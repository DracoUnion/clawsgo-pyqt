"""Basic contract and backend smoke tests for the standalone build."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC))
from service import Backend, command_names  # noqa: E402


def _fresh() -> Backend:
    """A backend on its own temp SQLite file so tests never contaminate each other."""
    tmp = tempfile.mkdtemp()
    return Backend(url=f"sqlite:///{tmp}/test.db")


class BackendSmokeTests(unittest.TestCase):
    def test_contract_registry_is_complete(self):
        contract = ROOT / 'contracts' / 'commands.json'
        if not contract.exists():
            self.skipTest('contracts/commands.json 不在本工作区，跳过契约完整性校验')
        expected = set(json.loads(contract.read_text(encoding='utf-8')))
        self.assertEqual(set(command_names()), expected)
        self.assertEqual(len(command_names()), 266)

    def test_boot_profile_and_chat(self):
        backend = _fresh()
        profile = backend.current_user()
        self.assertEqual(profile['role'], 'super_admin')
        conversations = backend.call('getConversations', {})
        self.assertTrue(conversations['conversations'])
        sent = backend.call('sendMessage', {'conversationId': 'c_demo', 'text': 'hello'})
        self.assertEqual(sent['assistantMessage']['role'], 'assistant')
        self.assertTrue(sent['assistantMessage']['parts'])

    def test_admin_profile(self):
        backend = _fresh()
        self.assertEqual(backend.current_user()['role'], 'super_admin')
        self.assertIn('items', backend.call('adminGetPaymentOrders', {}))

    # ------------------------------------------------------------------
    # domain coverage
    # ------------------------------------------------------------------
    def test_skills(self):
        b = _fresh()
        rows = b.call('getSkills', {})['skills']
        self.assertGreaterEqual(len(rows), 12)
        slug = rows[0]['slug']
        detail = b.call('getSkillDetail', {'slug': slug})['detail']
        self.assertIn('readme', detail)
        toggled = b.call('setSkillEnabled', {'slug': slug, 'enabled': False})['skill']
        self.assertFalse(toggled['enabled'])
        installed = b.call('installSkill', {'slug': 'meta-analysis'})['skill']
        self.assertTrue(installed['installed'])
        self.assertGreaterEqual(b.call('searchSkillMarket', {'query': '文献'})['total'], 1)

    def test_hosts(self):
        b = _fresh()
        created = b.call('createHost', {'kind': 'cloud', 'name': 't1', 'cpu': 4,
                                        'memoryGb': 8, 'diskGb': 100})['host']
        self.assertEqual(created['status'], 'running')
        env = b.call('getHostEnvironment', {'hostId': created['id']})['environment']
        self.assertEqual(env['os'], 'Ubuntu 24.04 LTS')
        storage = b.call('getHostStorage', {'hostId': created['id']})['storage']
        self.assertEqual(storage['totalGb'], 100)
        dirs = b.call('getHostDirectories', {'hostId': created['id'],
                                             'path': '/home/clawsgo/workspace'})
        self.assertTrue(dirs['exists'])
        self.assertTrue(dirs['entries'])
        self.assertTrue(b.call('deleteHost', {'hostId': created['id']})['ok'])

    def test_teams(self):
        b = _fresh()
        t = b.call('createTeam', {'name': '测试团队'})['team']
        self.assertEqual(t['role'], 'owner')
        inv = b.call('createTeamInvitation', {'teamId': t['id'], 'email': 'x@y.z'})['invitation']
        self.assertEqual(inv['status'], 'pending')
        self.assertGreaterEqual(b.call('getTeamMembers', {'teamId': t['id']})['total'], 1)

    def test_billing(self):
        b = _fresh()
        sub = b.call('getSubscription', {})['subscription']
        self.assertEqual(sub['planId'], 'pro')
        self.assertEqual(len(b.call('getPlans', {})['plans']), 6)
        order = b.call('createPaymentOrder', {'planId': 'ultra', 'months': 1})['order']
        self.assertEqual(order['status'], 'pending')
        self.assertEqual(order['amountCents'], 9990)
        invoice = b.call('createInvoice', {'amount': 2990, 'title': '演示'})['invoice']
        self.assertEqual(invoice['status'], 'requested')
        redeemed = b.call('redeemCode', {'code': 'CLAWSGO-DEMO-1000'})
        self.assertEqual(redeemed['credits'], 1000)

    def test_tickets(self):
        b = _fresh()
        t = b.call('createTicket', {'subject': '测试', 'body': '内容'})['ticket']
        self.assertEqual(t['status'], 'open')
        replied = b.call('replyTicket', {'id': t['id'], 'body': '追问'})['ticket']
        self.assertEqual(replied['unreadForUser'], 1)
        self.assertEqual(b.call('getTicket', {'id': t['id']})['unreadCount'], 1)

    def test_admin_actions(self):
        b = _fresh()
        self.assertEqual(b.call('adminCloseTicket', {'id': 't_ssh_offline'})['status'], 'closed')
        self.assertIn('codes', b.call('adminCreateRedeemCodes', {'count': 2, 'credits': 100}))


if __name__ == '__main__':
    unittest.main()