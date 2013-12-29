# -*- coding: utf-8 -*-
from __future__ import (print_function, division, absolute_import, unicode_literals)

from datetime import date
import json
import os.path
import re
import time
from urllib import urlencode
from urllib2 import urlopen
from urlparse import parse_qs
import unittest

from pmill import Paymill, PaymillError

BRIDGE_URL = "https://test-token.paymill.com/"


class MockPaymill(Paymill):
    def _api_call(self, endpoint, params=None, method='GET', headers=None,
    parse_json=True, return_type=None):
        opener, url, data = self._prepare_call(endpoint, params, method, headers)
        return {
            'endpoint': endpoint,
            'params': params,
            'method': method,
            'headers': headers,
            'parse_json': parse_json,
            'return_type': return_type,
            'opener': opener,
            'url': url,
            'data': data
        }


class MockTestCase(unittest.TestCase):
    def setUp(self):
        self.api = MockPaymill('fake-key')

    def assertEndpoint(self, _method, _endpoint, *args, **kwargs):
        r = getattr(self.api, _method)(*args, **kwargs)
        return self.assertEqual(r['endpoint'], _endpoint)

    def test_cards(self):
        r = self.api.new_card('tok_1234')
        self.assertEqual(r['endpoint'], 'payments/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']), {'token': ['tok_1234']})

        r = self.api.new_card('tok_1234', client='cli_1234')
        self.assertEqual(parse_qs(r['data']), {'token': ['tok_1234'], 'client': ['cli_1234']})

        r = self.api.get_card('card_1234')
        self.assertEqual(r['endpoint'], 'payments/card_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.get_cards(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'payments/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

        r = self.api.delete_card('card_1234')
        self.assertEqual(r['endpoint'], 'payments/card_1234')
        self.assertEqual(r['method'], 'DELETE')

    def test_transactions(self):
        r = self.api.new_transaction()
        self.assertEqual(r, None)

        r = self.api.new_transaction(amount=3000, payment='pay_1234')
        self.assertEqual(r['endpoint'], 'transactions/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']),
            {'currency': ['EUR'], 'amount': ['3000'], 'payment': ['pay_1234']})

        r = self.api.get_transaction('tran_1234')
        self.assertEqual(r['endpoint'], 'transactions/tran_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.update_transaction('tran_1234', 'desc')
        self.assertEqual(r['endpoint'], 'transactions/tran_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']), {'description': ['desc']})

        r = self.api.get_transactions(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'transactions/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

    def test_refunds(self):
        r = self.api.refund('tran_1234', 3000)
        self.assertEqual(r['endpoint'], 'refunds/tran_1234')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']), {'amount': ['3000']})

        r = self.api.get_refund('ref_1234')
        self.assertEqual(r['endpoint'], 'refunds/ref_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.get_refunds(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'refunds/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

    def test_preauthorize(self):
        r = self.api.preauthorize()
        self.assertEqual(r, None)
        self.assertRaises(ValueError, self.api.preauthorize, amount=3000)

        r = self.api.preauthorize(amount=3000, token='tok_1234')
        self.assertEqual(r['endpoint'], 'preauthorizations/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']),
            {'currency': ['EUR'], 'amount': ['3000'], 'token': ['tok_1234']})

        r = self.api.get_preauthorization('pre_1234')
        self.assertEqual(r['endpoint'], 'preauthorizations/pre_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.get_preauthorizations(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'preauthorizations/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

        r = self.api.delete_preauthorization('pre_1234')
        self.assertEqual(r['endpoint'], 'preauthorizations/pre_1234')
        self.assertEqual(r['method'], 'DELETE')

    def test_clients(self):
        r = self.api.new_client()
        self.assertEqual(r, None)

        r = self.api.new_client(email='test@example.net')
        self.assertEqual(r['endpoint'], 'clients/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']), {'email': ['test@example.net']})

        r = self.api.get_client('cli_1234')
        self.assertEqual(r['endpoint'], 'clients/cli_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.update_client('cli_1234')
        self.assertEqual(r, None)

        r = self.api.update_client('cli_1234', email='test@example.net')
        self.assertEqual(r['endpoint'], 'clients/cli_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']), {'email': ['test@example.net']})

        r = self.api.delete_client('cli_1234')
        self.assertEqual(r['endpoint'], 'clients/cli_1234')
        self.assertEqual(r['method'], 'DELETE')

        r = self.api.get_clients(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'clients/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

        r = self.api.export_clients()
        self.assertEqual(r['endpoint'], 'clients/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(dict(r['opener'].addheaders)['Accept'], 'text/csv')

    def test_offers(self):
        r = self.api.new_offer(0, 'foo')
        self.assertEqual(r, None)

        self.assertRaises(ValueError, self.api.new_offer, amount='foo', name='bar')
        self.assertRaises(ValueError, self.api.new_offer, amount='10.10', name='bar')
        self.assertRaises(ValueError, self.api.new_offer, amount=20, interval='foo', name='bar')

        r = self.api.new_offer(amount=3000, name='test')
        self.assertEqual(r['endpoint'], 'offers/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']),
            {'currency': ['EUR'], 'amount': ['3000'], 'interval': ['month'], 'name': ['test']})

        r = self.api.get_offer('offer_1234')
        self.assertEqual(r['endpoint'], 'offers/offer_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.update_offer('offer_1234', name='foo')
        self.assertEqual(r['endpoint'], 'offers/offer_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']), {'name': ['foo']})

        r = self.api.delete_offer('offer_1234')
        self.assertEqual(r['endpoint'], 'offers/offer_1234')
        self.assertEqual(r['method'], 'DELETE')

        r = self.api.get_offers(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'offers/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

    def test_subscriptions(self):
        today = date.today()
        ts = re.sub(r'\..*$', '', str(time.mktime(today.timetuple())))

        r = self.api.new_subscription('cli_1234', 'offer_1234', 'pay_1234', today)
        self.assertEqual(r['endpoint'], 'subscriptions/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']), {
            'client': ['cli_1234'], 'payment': ['pay_1234'], 'offer': ['offer_1234'],
            'start_at': [ts]
        })

        r = self.api.get_subscription('sub_1234')
        self.assertEqual(r['endpoint'], 'subscriptions/sub_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.update_subscription('sub_1234', 'offer_1234')
        self.assertEqual(r['endpoint'], 'subscriptions/sub_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']), {'offer': ['offer_1234']})

        r = self.api.cancel_subscription_after_interval('sub_1234', True)
        self.assertEqual(r['endpoint'], 'subscriptions/sub_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']), {'cancel_at_period_end': ['true']})

        r = self.api.cancel_subscription_now('sub_1234')
        self.assertEqual(r['endpoint'], 'subscriptions/sub_1234')
        self.assertEqual(r['method'], 'DELETE')

        r = self.api.get_subscriptions(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'subscriptions/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})

    def test_webhooks(self):
        self.assertRaises(ValueError, self.api.new_webhook, ['test'])

        r = self.api.new_webhook(['foo', 'bar'], url='http://example.net/')
        self.assertEqual(r['endpoint'], 'webhooks/')
        self.assertEqual(r['method'], 'POST')
        self.assertEqual(parse_qs(r['data']),
            {'url': ['http://example.net/'], 'event_types[]': ['foo', 'bar']})

        r = self.api.get_webhook('hook_1234')
        self.assertEqual(r['endpoint'], 'webhooks/hook_1234')
        self.assertEqual(r['method'], 'GET')

        r = self.api.update_webhook('hook_1234', ['foo', 'bar'], url='http://example.net/')
        self.assertEqual(r['endpoint'], 'webhooks/hook_1234')
        self.assertEqual(r['method'], 'PUT')
        self.assertEqual(parse_qs(r['data']),
            {'url': ['http://example.net/'], 'event_types[]': ['foo', 'bar']})

        r = self.api.delete_webhook('hook_1234')
        self.assertEqual(r['endpoint'], 'webhooks/hook_1234')
        self.assertEqual(r['method'], 'DELETE')

        r = self.api.get_webhooks(count=1, offset=5)
        self.assertEqual(r['endpoint'], 'webhooks/')
        self.assertEqual(r['method'], 'GET')
        self.assertEqual(r['params'], {'count': 1, 'offset': 5})


class LiveTestCase(unittest.TestCase):
    def setUp(self):
        key_file = os.path.join(os.path.dirname(__file__), 'keys')
        try:
            with open(key_file, 'r') as fp:
                keys = fp.read().split('\n')
                public_key = keys[0].strip()
                private_key = keys[1].strip()
        except:
            raise SystemExit('ERROR: Please create a file named "keys" with your public key on '
                + 'the first line and your private key on the second line.')

        self.public_key = public_key
        self.api = Paymill(private_key)

    def call_bridge(self, number, cvc, amount, currency='EUR',
    exp_month=None, exp_year=None, holder=None):
        exp_month = exp_month or date.today().month
        exp_year = exp_year or date.today().year
        holder = holder or 'John Doe'

        params = {
            'transaction.mode': 'CONNECTOR_TEST',
            'channel.id': self.public_key,
            'account.number': number,
            'account.verification': cvc,
            'account.expiry.month': exp_month,
            'account.expiry.year': exp_year,
            'account.holder': holder,
            'presentation.amount3D': amount,
            'presentation.currency3D': currency
        }
        url = '{0}?{1}'.format(BRIDGE_URL, urlencode(params))
        fp = urlopen(url)
        return json.load(fp)

    def test_cards(self):
        data = self.call_bridge('4111111111111111', '123', '3000')
        token = data['transaction']['identification']['uniqueId']

        card_list = self.api.get_cards(order='created_at_desc')
        card_count = card_list.data_count

        card = self.api.new_card(token)
        card_list = self.api.get_cards(order='created_at_desc')
        self.assertEqual(card_list.data_count, card_count + 1)
        self.assertTrue(card.id is not None)

        passed = False
        try:
            self.api.new_card('tok_123')
        except PaymillError as e:
            self.assertEqual(e.args[1], 404)
            self.assertEqual(e.args[2], 'Not Found')
            self.assertEqual(e.data, 'Token not Found')
            passed = True

        self.assertTrue(passed)

    def test_transactions(self):
        data = self.call_bridge('4111111111111111', '123', '3000')
        token = data['transaction']['identification']['uniqueId']

        transaction_list = self.api.get_transactions(order='created_at_desc', count=1)
        transaction_count = transaction_list.data_count

        transaction = self.api.new_transaction(
            amount=2000, currency='EUR', token=token, holder='John Doe')

        transaction_list = self.api.get_transactions(order='created_at_desc', count=1)
        self.assertEqual(transaction_list.data_count, transaction_count + 1)
        self.assertEqual(transaction.id, transaction_list[0].id)

        transaction = self.api.get_transaction(transaction.id)
        self.assertTrue(transaction.id is not None)
        self.assertEqual(transaction.description, None)

        transaction = self.api.update_transaction(transaction.id, 'Test desc')
        self.assertEqual(transaction.description, 'Test desc')
        transaction = self.api.get_transaction(transaction.id)
        self.assertEqual(transaction.description, 'Test desc')

        refund_list = self.api.get_refunds(order='created_at_desc', count=1)
        refund_count = refund_list.data_count

        refund = self.api.refund(transaction.id, amount=2000)
        self.assertEqual(int(refund.amount), 2000)

        transaction = self.api.get_transaction(transaction.id)
        self.assertEqual(int(transaction.amount), 000)

        refund = self.api.get_refund(refund.id)
        self.assertEqual(int(refund.amount), 2000)

        refund_list = self.api.get_refunds(order='created_at_desc', count=1)
        self.assertEqual(refund_list.data_count, refund_count + 1)

    def test_preauthorize(self):
        data = self.call_bridge('4111111111111111', '123', '3000')
        token = data['transaction']['identification']['uniqueId']

        transaction = self.api.preauthorize(amount=2000, token=token)
        self.assertTrue(transaction.preauthorization.id is not None)

        self.api.delete_preauthorization(transaction.preauthorization.id)

        data = self.call_bridge('4111111111111111', '123', '3000')
        token = data['transaction']['identification']['uniqueId']

        transaction = self.api.preauthorize(amount=2000, token=token)
        transaction_id = transaction.id

        transaction = self.api.new_transaction(
            amount=4000, preauth=transaction.preauthorization, holder='John Doe'
        )
        self.assertEqual(transaction_id, transaction.id)

        preauthorization_list = self.api.get_preauthorizations()
        self.assertTrue(preauthorization_list.data_count > 0)

        preauthorization = self.api.get_preauthorization(transaction.preauthorization.id)
        self.assertEqual(transaction.preauthorization.id, preauthorization.id)

    def test_clients(self):
        client = self.api.new_client(email='test@example.net', description='foo')
        self.assertTrue(client.id is not None)

        client = self.api.get_client(client.id)
        self.assertEqual(client.email, 'test@example.net')
        self.assertEqual(client.description, 'foo')

        client = self.api.update_client(client.id, description='woot')
        client = self.api.get_client(client.id)
        self.assertEqual(client.description, 'woot')

        client_list = self.api.get_clients()
        self.assertTrue(client_list.data_count > 0)

        csv = self.api.export_clients()
        self.assertTrue(csv.split('\n')[0].startswith('"id";"email"'))

        self.api.delete_client(client.id)
        self.assertRaises(PaymillError, self.api.get_client, client.id)

    def test_offers(self):
        offer = self.api.new_offer(amount=3000, name='foo', interval='2 week')
        self.assertEqual(offer.amount, '3000')
        self.assertEqual(offer.name, 'foo')
        self.assertEqual(offer.interval, '2 WEEK')

        offer = self.api.get_offer(offer.id)
        self.assertEqual(offer.name, 'foo')

        offer = self.api.update_offer(offer.id, name='bar')
        self.assertEqual(offer.name, 'bar')

        offer_list = self.api.get_offers()
        self.assertTrue(offer_list.data_count > 0)

        self.api.delete_offer(offer.id)

    def test_subscriptions(self):
        data = self.call_bridge('4111111111111111', '123', '3000')
        token = data['transaction']['identification']['uniqueId']

        client = self.api.new_client(email='test@example.net', description='foo')
        card = self.api.new_card(token=token, client=client.id)

        offer = self.api.new_offer(amount=2000, name='foo', interval='2 week')
        subscription = self.api.new_subscription(
            client=client, offer=offer, payment=card
        )

        subscription = self.api.get_subscription(subscription.id)
        self.assertEqual(subscription.offer.id, offer.id)

        self.api.update_subscription(subscription.id, offer)
        self.api.cancel_subscription_after_interval(subscription.id)

        self.api.cancel_subscription_now(subscription.id)
        self.api.delete_offer(offer.id)
        self.api.delete_client(client.id)

        subscription_list = self.api.get_subscriptions()
        self.assertTrue(subscription_list.data_count > 0)

    def test_webhooks(self):
        hook = self.api.new_webhook(['chargeback.executed', 'transaction.created'],
            url='http://example.net/')
        self.assertTrue(hook.id is not None)

        hook_list = self.api.get_webhooks()
        self.assertTrue(hook_list.data_count > 0)

        hook = self.api.get_webhook(hook.id)
        hook = self.api.update_webhook(hook.id, hook.event_types, url='http://example.org/')
        self.assertEqual(hook.url, 'http://example.org/')

        self.api.delete_webhook(hook.id)

    def test_errors(self):
        pass


if __name__ == '__main__':
    unittest.main()
