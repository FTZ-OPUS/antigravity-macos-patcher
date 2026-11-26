import os
import sys
import tempfile
import unittest
from unittest import mock

# 让 source 目录可导入
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(ROOT, "source")
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import auto_patch
import patch_ops as ops
from patcher.manager import discovery as mgr_discovery


# 构造一个满足 > 1MB 且包含真实 MANAGER_GATE_X64 字节特征的模拟二进制
X64_UNPATCHED_SIG = b"\x80\x78\x08\x00\x74\x12\x48\x8b\x44\x24\x10\x48\x89\x44\x60"
PADDING = b"\x00" * (1024 * 1024 + 4096)


def make_fake_binary(path, with_sig=True):
    payload = (PADDING + X64_UNPATCHED_SIG + b"\x90" * 64) if with_sig else (PADDING + b"\x90" * 64)
    with open(path, "wb") as f:
        f.write(payload)


class AutoPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmpdir.name, "appdata")
        os.makedirs(self.data_dir, exist_ok=True)
        self.bin_path = os.path.join(self.tmpdir.name, "language_server.exe")

        self.p_data_dir = mock.patch.object(auto_patch, "app_data_dir", return_value=self.data_dir)
        self.p_notify = mock.patch.object(auto_patch, "notify")
        self.p_data_dir.start()
        self.p_notify.start()

    def tearDown(self):
        self.p_data_dir.stop()
        self.p_notify.stop()
        self.tmpdir.cleanup()

    def test_auto_patch_on_fresh_and_updated_binary(self):
        make_fake_binary(self.bin_path, with_sig=True)
        self.assertEqual(ops.state_of(self.bin_path), "unpatched")

        # 1. 首次检测到未打补丁 → 自动打补丁成功
        status, detail = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=True,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status, "patched", detail)
        self.assertEqual(ops.state_of(self.bin_path), "patched")
        self.assertTrue(ops.has_backup(self.bin_path))

        # 2. 已经打过补丁 → 再次检测直接跳过
        status2, _ = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=False,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status2, "already_patched")

        # 3. 模拟 Antigravity 软件更新（覆盖回新版原版文件）
        make_fake_binary(self.bin_path, with_sig=True)
        self.assertEqual(ops.state_of(self.bin_path), "unpatched")

        # 4. 再次检测 → 自动重新打补丁成功
        status3, detail3 = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=True,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status3, "patched", detail3)
        self.assertEqual(ops.state_of(self.bin_path), "patched")

    def test_unknown_version_skips_retry_until_file_changes(self):
        make_fake_binary(self.bin_path, with_sig=False)
        self.assertEqual(ops.state_of(self.bin_path), "unknown")

        # 首次遇到未知版本 → 返回 failed 并记录指纹
        status, _ = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=True,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status, "failed")
        cfg = auto_patch.load_config()
        self.assertTrue(cfg["failed_fingerprint"])

        # 文件未变 → 第二次应跳过，不死循环重试
        status2, _ = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=True,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status2, "skipped_failed")

        # 模拟更新为可识别的新版本（大小不同导致指纹变化）
        make_fake_binary(self.bin_path, with_sig=True)
        status3, detail3 = auto_patch.check_and_auto_patch(
            target=self.bin_path,
            wait_stable=False,
            send_notification=True,
            manage_app_lifecycle=False,
        )
        self.assertEqual(status3, "patched", detail3)
        self.assertEqual(auto_patch.load_config()["failed_fingerprint"], "")

    def test_config_roundtrip(self):
        cfg = auto_patch.load_config()
        self.assertFalse(cfg["enabled"])
        cfg["enabled"] = True
        cfg["interval"] = 20
        auto_patch.save_config(cfg)

        loaded = auto_patch.load_config()
        self.assertTrue(loaded["enabled"])
        self.assertEqual(loaded["interval"], 20)

    def test_win_all_drives_discovery(self):
        # 模拟 D 盘自定义深层目录：fake_D\MySoft\AI\Antigravity\resources\bin\language_server.exe
        fake_c = os.path.join(self.tmpdir.name, "fake_C")
        fake_d = os.path.join(self.tmpdir.name, "fake_D")
        target = os.path.join(fake_d, "MySoft", "AI", "Antigravity", "resources", "bin", "language_server.exe")
        os.makedirs(fake_c, exist_ok=True)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(b"fake")

        rel = os.path.join("resources", "bin", "language_server.exe")
        with mock.patch.object(mgr_discovery, "_win_logical_drives", return_value=[fake_c, fake_d]):
            hits = mgr_discovery._win_scan_all_drives_for_manager(rel)
        self.assertIn(target, hits)

    def test_extract_dir_from_reg_value(self):
        exe_dir = os.path.join(self.tmpdir.name, "reg_app")
        os.makedirs(exe_dir, exist_ok=True)
        fake_exe = os.path.join(exe_dir, "Antigravity.exe")
        with open(fake_exe, "wb") as f:
            f.write(b"fake")

        self.assertEqual(
            mgr_discovery._extract_dir_from_reg_value(f'"{fake_exe}",0'),
            exe_dir,
        )
        self.assertEqual(
            mgr_discovery._extract_dir_from_reg_value(f'"{fake_exe}" /S'),
            exe_dir,
        )
        self.assertEqual(
            mgr_discovery._extract_dir_from_reg_value(f"{fake_exe},0"),
            exe_dir,
        )


if __name__ == "__main__":
    unittest.main()
