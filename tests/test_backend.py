"""Basic contract and backend smoke tests for the standalone build."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui.backend import Backend, command_names  # noqa: E402

class BackendSmokeTests(unittest.TestCase):
    def test_contract_registry_is_complete(self):
        contract = ROOT / 'contracts' / 'commands.json'
        if not contract.exists():
            self.skipTest('contracts/commands.json 不在本工作区，跳过契约完整性校验')
        expected = set(json.loads(contract.read_text(encoding='utf-8')))
        self.assertEqual(set(command_names()), expected)
        self.assertEqual(len(command_names()), 266)

    def test_demo_auth_and_chat(self):
        backend = Backend()
        result = backend.login_password('13800000000', 'clawsgo2026')
        self.assertEqual(result['user']['id'], 'u_demo')
        conversations = backend.call('getConversations', {})
        self.assertTrue(conversations['conversations'])
        sent = backend.call('sendMessage', {'conversationId': 'c_demo', 'text': 'hello'})
        self.assertEqual(sent['assistantMessage']['role'], 'assistant')
        self.assertTrue(sent['assistantMessage']['parts'])

    def test_admin_login(self):
        backend = Backend()
        result = backend.login_password('13900000000', 'clawsgo2026')
        self.assertEqual(result['user']['role'], 'super_admin')
        self.assertIn('items', backend.call('adminGetUsers', {}))

if __name__ == '__main__':
    unittest.main()
