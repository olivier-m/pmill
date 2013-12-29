# -*- coding: utf-8 -*-
from __future__ import (print_function, division, absolute_import, unicode_literals)

import base64
from datetime import date, datetime
import json
import logging
import re
import time
from urllib import urlencode
from urllib2 import (
    build_opener, Request, HTTPError,
    HTTPSHandler, HTTPDefaultErrorHandler, HTTPErrorProcessor
)

__all__ = ('Paymill', 'PaymillError')

BASE_URL = 'https://api.paymill.com/v2/'
LOGGER = logging.getLogger(__name__)

ERRORS = {
    401: 'Unauthorized',
    403: 'Transaction Error',
    404: 'Not Found',
    412: 'Precondition Failed',
    500: 'Server Error',
}

DETAILED_ERRORS = {
    40000: 'General problem with data.',
    40001: 'General problem with payment data.',
    40100: 'Problem with credit card data.',
    40101: 'Problem with cvv.',
    40102: 'Card expired or not yet valid.',
    40103: 'Limit exceeded.',
    40104: 'Card invalid.',
    40105: 'Expiry date not valid.',
    40106: 'Credit card brand required.',
    40200: 'Problem with bank account data.',
    40201: 'Bank account data combination mismatch.',
    40202: 'User authentication failed.',
    40300: 'Problem with 3d secure data.',
    40301: 'Currency / amount mismatch',
    40400: 'Problem with input data.',
    40401: 'Amount too low or zero.',
    40402: 'Usage field too long.',
    40403: 'Currency not allowed.',
    50000: 'General problem with backend.',
    50001: 'Country blacklisted.',
    50100: 'Technical error with credit card.',
    50101: 'Error limit exceeded.',
    50102: 'Card declined by authorization system.',
    50103: 'Manipulation or stolen card.',
    50104: 'Card restricted.',
    50105: 'Invalid card configuration data.',
    50200: 'Technical error with bank account.',
    50201: 'Card blacklisted.',
    50300: 'Technical error with 3D secure.',
    50400: 'Decline because of risk issues.',
    50500: 'General timeout.',
    50501: 'Timeout on side of the acquirer.',
    50502: 'Risk management transaction timeout.',
    50600: 'Duplicate transaction.',
}

RE_INT = re.compile(r'^[0-9]+$')
RE_INTERVAL = re.compile(r'^[0-9]*\ ?(DAY|WEEK|MONTH|YEAR)$', re.I)


class HTTPRequest(Request):
    def __init__(self, method=None, *args, **kwargs):
        Request.__init__(self, *args, **kwargs)
        self.method = method

    def get_method(self):
        return self.method or super(HTTPRequest, self).get_method()


class PaymillError(Exception):
    def __init__(self, code, message, data=None):
        super(PaymillError, self).__init__(self, code, message)
        self.data = data


class PaymillObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()

    def _iterencode(self, obj, markers=None):
        if isinstance(obj, PaymillObject):
            for i, x in enumerate(super(PaymillObjectEncoder, self)
            ._iterencode(obj.__dict__, markers)):
                if i == 1:
                    yield '  // {0}'.format(type(obj))
                yield x
        else:
            for x in super(PaymillObjectEncoder, self)._iterencode(obj, markers):
                yield x


class PaymillBase(type):
    def __new__(cls, name, bases, attrs):
        meta = attrs.pop('Meta', None)
        attrs['_base_fields'] = {}
        attrs['_typed_fields'] = {}

        fields = getattr(meta, 'fields', [])
        typed_fields = getattr(meta, 'typed_fields', {})

        for f in fields:
            if f in typed_fields:
                attrs['_typed_fields'][f] = typed_fields[f]

            attrs['_base_fields'][f] = None

        new_class = super(PaymillBase, cls).__new__(cls, name, bases, attrs)
        return new_class


class PaymillObject(object):
    """Base class for all Paymill data objects"""
    __metaclass__ = PaymillBase

    def __init__(self, **kwargs):
        self.__dict__.update(self._base_fields)
        self.__dict__.update(kwargs)

        for k, v in self._typed_fields.items():
            if k in self.__dict__ and self.__dict__[k] is not None:
                callback = globals()[v]

                if isinstance(self.__dict__[k], (list, tuple)):
                    self.__dict__[k] = [
                        callback(**x) for x in self.__dict__[k]
                        if isinstance(x, dict)
                    ]
                elif isinstance(self.__dict__[k], dict):
                    self.__dict__[k] = callback(**self.__dict__[k])

        for x in ('created_at', 'updated_at'):
            if x in self.__dict__:
                self.__dict__[x] = datetime.fromtimestamp(self.__dict__[x])

    def __str__(self):
        if hasattr(self, 'id'):
            return self.id
        return super(PaymillObject, self).__str__()

    def __repr__(self):
        return json.dumps(self, cls=PaymillObjectEncoder, indent=2)


class PaymillList(list):
    def __init__(self, data_count, iterable=None):
        super(PaymillList, self).__init__(iterable)
        self.data_count = data_count


class Client(PaymillObject):
    class Meta:
        fields = (
            'id',            # unique id for this client
            'email',         # client's email address (optional)
            'description',   # description of this client (optional)
            'payment',       # list of cc or debit objects
            'subscription',  # subscription object (optional)
            'created_at',    # unix timestamp identifying time of creation
            'updated_at',    # unix timestamp identifying time of last change
        )
        typed_fields = {
            'payment': 'Payment',
            'subscription': 'Subscription',
        }


class Offer(PaymillObject):
    class Meta:
        fields = (
            'id',                  # string Unique identifier of this offer
            'name',                # string Your name for this offer
            'amount',              # integer (>0) Every interval the specified amount will be
                                   # charged. Only integer values are allowed (e.g. 42.00 = 4200)
            'interval',            # string Defining how often the client should be charged.
                                   # Format: number DAY | WEEK | MONTH | YEAR Example: 2 DAY
            'trial_period_days',   # integer or null Give it a try or charge directly?
            'created_at',          # integer Unix-Timestamp for the creation Date
            'updated_at',          # integer Unix-Timestamp for the last update
            'subscription_count',  # subscription_count Attributes: (integer) if zero,
                                   # else (string) active, (integer) if zero, else (string) inactive
            'app_id',              # string or null App (ID) that created this offer
                                   # or null if created by yourself.
        )


class Payment(PaymillObject):
    class Meta:
        fields = (
            'id',                  # unique payment method ID"""
            'type',                # creditcard or debit
            'client',              # id of associatied client (optional)
            'card_type',           # visa or mastercard (for credit cards only)
            'country',             # country the card was issued in (For credit cards only)
            'expire_month',        # 2 digits (For credit cards only)
            'expire_year',         # 4 digitis (For credit cards only)
            'card_holder',         # name of cardholder (For credit cards only)
            'last4',               # last 4 digits of card (For credit cards only)
            'code',                # the sorting code of the bank (For debit accounts only)
            'account',             # a partially masked account number (For debit accounts only)
            'holder',              # name of the account holder (For debit accounts only)
            'created_at',          # unix timestamp identifying time of creation
            'updated_at',          # unix timestamp identifying time of last change
            'app_id',              # string or null App (ID) that created this payment
                                   # or null if created by yourself.
        )


class Preauthorization(PaymillObject):
    class Meta:
        fields = (
            'id',          # unique preauthorization ID
            'amount',      # amount preauthorized in CENTS
            'status',      # open, pending, closed, failed, deleted, or preauth
            'livemode',    # true or false depending on whether the transaction is real
                           # or in test mode
            'payment',     # a credit card payment method object (see above)
            'client',      # if a preset client (see below) was used to make the
                           # transaction. Otherwise null
            'created_at',  # unix timestamp identifying time of creation
            'updated_at',  # unix timestamp identifying time of last change
            'app_id',      # string or null App (ID) that created this payment
                           # or null if created by yourself.
        )
        typed_fields = {
            'payment': 'Payment',
            'client': 'Client',
        }


class Transaction(PaymillObject):
    class Meta:
        fields = (
            'id',                # string Unique identifier of this transaction.
            'amount',            # string Formatted amount of this transaction.
            'origin_amount',     # integer (>0) The used amount, smallest possible unit per currency
                                 # (for euro, we’re calculating the amount in cents).
            'currency',          # string ISO 4217 formatted currency code.
            'status',            # enum(open, pending, closed, failed, partial_refunded, refunded,
                                 # preauthorize, chargeback) Indicates the current status of this
                                 # transaction, e.g closed means the transaction is sucessfully
                                 # transfered, refunded means that the amount is fully or in parts
                                 # refunded.
            'description',       # string or null Need a additional description for this
                                 # transaction? Maybe your shopping cart ID or something like that?
            'livemode',          # boolean Whether this transaction was issued while being in live
                                 # mode or not.
            'is_fraud',          # boolean The transaction is marked as fraud or not.
            'refunds',           # list refund objects or null
            'payment',           # creditcard-object or directdebit-object
            'client',            # clients-object or null
            'preauthorization',  # preauthorizations-object or null
            'created_at',        # integer Unix-Timestamp for the creation date.
            'updated_at',        # integer Unix-Timestamp for the last update.
            'response_code',     # integer Response code
            'short_id',          # string Unique identifier of this transaction provided to the
                                 # acquirer for the statements.
            'invoices',          # list PAYMILL invoice where the transaction fees are charged
                                 # or null.
            'fees',              # list App fees or null.
            'app_id',            # string or null App (ID) that created this transaction or null if
                                 # created by yourself.
        )
        typed_fields = {
            'payment': 'Payment',
            'client': 'Client',
            'preauthorization': 'Preauthorization',
            'refunds': 'Refund',
        }


class Refund(PaymillObject):
    class Meta:
        fields = (
            'id',           # unique refund ID
            'transaction',  # The unique transaction ID of the transaction being refunded
            'amount',       # amount refunded in CENTS
            'status',       # open, pending or refunded
            'description',  # user-selected description of the refund
            'livemode',     # true or false depending on whether the transaction
                            # is real or in test mode
            'created_at',   # unix timestamp identifying time of creation
            'updated_at',   # unix timestamp identifying time of last change
        )


class Subscription(PaymillObject):
    class Meta:
        fields = (
            'id',                    # string Unique identifier of this subscription.
            'offer',                 # offer object
            'livemode',              # boolean Whether this subscription was issued while being in
                                     # live mode or not.
            'cancel_at_period_end',  # boolean Cancel this subscription immediately or at the end
                                     # of the current period?
            'trial_start',           # integer or null Unix-Timestamp for the trial period start
            'trial_end',             # integer or null Unix-Timestamp for the trial period end.
            'next_capture_at',       # integer Unix-Timestamp for the next charge.
            'created_at',            # integer Unix-Timestamp for the creation Date.
            'updated_at',            # integer Unix-Timestamp for the last update.
            'canceled_at',           # integer or null Unix-Timestamp for the cancel date.
            'payment',               # payment object for credit card or payment object for
                                     # direct debit
            'client',                # client object
            'app_id',                # string or null App (ID) that created this subscription or
                                     # null if created by yourself.
        )
        typed_fields = {
            'offer': 'Offer',
            'payment': 'Payment',
            'client': 'Client',
        }

    def __init__(self, **kwargs):
        super(Subscription, self).__init__(**kwargs)
        if self.offer == []:
            self.offer = None


class Webhook(PaymillObject):
    class Meta:
        fields = (
            'id',           # string Unique identifier of this webhook
            'url',          # string the url of the webhook
            'email',        # string either the email OR the url have to be set and will be returned
            'livemode',     # you can create webhooks for livemode and testmode
            'event_types',  # array of event_types
            'app_id',       # string or null App (ID) that created this webhook or null if
                            # created by yourself.
        )


class Paymill(object):
    EMPTY = (None, str(None), '', [])

    def __init__(self, private_key):
        self.private_key = private_key

    def _urlencode(self, params, doseq=True):
        """urlencode after removing empty and null values"""
        _tmp = []
        if isinstance(params, dict):
            params = params.iteritems()

        for k, v in params:
            if isinstance(v, (list, tuple)):
                v = [x for x in v if x not in self.EMPTY]
                if not k.endswith('[]'):
                    k = '{0}[]'.format(k)

            if v not in self.EMPTY:
                _tmp.append((k, v))

        return urlencode(_tmp, doseq)

    def _handler_error(self, e):
        code = e.getcode()
        err_data = None

        try:
            json_data = json.load(e)
            if 'error' in json_data:
                err_data = json_data['error']
            if 'data' in json_data:
                err_data = json_data['data']
                code = err_data.get('response_code', code)
        except:
            pass

        msg = '{0}'.format(e)
        if code in ERRORS:
            msg = ERRORS[code]
        elif code in DETAILED_ERRORS:
            msg = DETAILED_ERRORS[code]

        if code // 100 == 5:
            msg = ERRORS[500]

        raise PaymillError(code, msg, err_data)

    def _prepare_call(self, endpoint, params, method, headers):
        opener = build_opener(HTTPSHandler, HTTPDefaultErrorHandler, HTTPErrorProcessor)

        auth = base64.standard_b64encode('{0}:'.format(self.private_key))
        _headers = {
            'Authorization': 'Basic {0}'.format(auth)
        }
        _headers.update(headers or {})
        opener.addheaders = _headers.items()

        url = '{0}{1}'.format(BASE_URL, endpoint)
        data = None
        if params:
            params = self._urlencode(params)
            if method in ('POST', 'PUT'):
                data = params
            else:
                url = '{0}?{1}'.format(url, params)

        return (opener, url, data)

    def _api_call(self, endpoint, params=None, method='GET', headers=None,
    parse_json=True, return_type=None):
        opener, url, data = self._prepare_call(endpoint, params, method, headers)
        req = HTTPRequest(url=url, method=method, data=data)

        try:
            response = opener.open(req)
            if response.getcode() != 200:
                raise PaymillError(response.getcode(), 'Unknown error')
        except HTTPError as e:
            self._handler_error(e)

        try:
            if parse_json:
                json_data = json.load(response)
                if 'data' in json_data:
                    if return_type:
                        if isinstance(json_data['data'], dict):
                            return return_type(**json_data['data'])
                        elif isinstance(json_data['data'], (list, tuple)):
                            return PaymillList(
                                int(json_data.get('data_count', 0)),
                                [return_type(**x) for x in json_data['data']]
                            )
                    else:
                        return json_data
                else:
                    raise Exception(json_data)

            return response.read()
        finally:
            response.close()

    #
    # Payments
    #
    def new_card(self, token, client=None):
        return self._api_call('payments/',
            params={'token': token, 'client': client},
            return_type=Payment,
            method='POST'
        )

    def get_card(self, card_id):
        return self._api_call('payments/{0}'.format(card_id), return_type=Payment)

    def get_cards(self, **params):
        return self._api_call('payments/', params=params, return_type=Payment)

    def delete_card(self, card_id):
        return self._api_call('payments/{0}'.format(card_id),
            return_type=Payment,
            method='DELETE'
        )

    #
    # Transactions
    #
    def new_transaction(self, amount=0, currency='EUR', description=None, token=None, client=None,
    payment=None, preauth=None, code=None, account=None, holder=None):
        if amount == 0:
            return None

        params = {
            'amount': amount, 'currency': currency, 'client': client, 'description': description
        }

        # figure out mode of payment
        if payment is not None:
            params['payment'] = payment
        elif token is not None:
            params['token'] = token
        elif preauth is not None:
            params['preauthorization'] = (
                isinstance(preauth, Preauthorization) and preauth.id or preauth
            )
        else:
            return None

        return self._api_call('transactions/',
            params=params, return_type=Transaction, method='POST'
        )

    def get_transaction(self, transaction_id):
        return self._api_call('transactions/{0}'.format(transaction_id), return_type=Transaction)

    def update_transaction(self, transaction_id, description):
        return self._api_call('transactions/{0}'.format(transaction_id),
            return_type=Transaction,
            params={'description': description},
            method='PUT'
        )

    def get_transactions(self, **params):
        return self._api_call('transactions/', params=params, return_type=Transaction)

    #
    # Refunds
    #
    def refund(self, transaction_id, amount, description=None):
        if amount == 0:
            return None

        return self._api_call('refunds/{0}'.format(transaction_id),
            params={'amount': amount, 'description': description},
            return_type=Refund,
            method='POST'
        )

    def get_refund(self, refund_id):
        return self._api_call('refunds/{0}'.format(refund_id), return_type=Refund)

    def get_refunds(self, **params):
        return self._api_call('refunds/', params=params, return_type=Refund)

    #
    # Preauthorizations
    #
    def preauthorize(self, amount=0, currency='EUR', description=None, token=None,
    client=None, payment=None):
        if amount == 0:
            return
        if (payment is None and token is None) or (payment is not None and token is not None):
            raise ValueError('Please only provide token OR payment.')

        return self._api_call('preauthorizations/',
            params={'amount': amount, 'currency': currency, 'payment': payment, 'token': token},
            return_type=Transaction,
            method='POST'
        )

    def get_preauthorization(self, preauth_id):
        return self._api_call('preauthorizations/{0}'.format(preauth_id),
            return_type=Preauthorization
        )

    def get_preauthorizations(self, **params):
        return self._api_call('preauthorizations/', params=params, return_type=Preauthorization)

    def delete_preauthorization(self, preauth_id):
        return self._api_call('preauthorizations/{0}'.format(preauth_id),
            return_type=Preauthorization,
            method='DELETE'
        )

    #
    # Clients
    #
    def new_client(self, email=None, description=None):
        if email is None and description is None:
            return None

        return self._api_call('clients/',
            params={'email': email, 'description': description},
            return_type=Client,
            method='POST'
        )

    def get_client(self, client_id):
        return self._api_call('clients/{0}'.format(client_id), return_type=Client)

    def update_client(self, client_id, email=None, description=None):
        if email is None and description is None:
            return None

        return self._api_call('clients/{0}'.format(client_id),
            params={'email': email, 'description': description},
            return_type=Client,
            method='PUT'
        )

    def delete_client(self, client_id):
        return self._api_call('clients/{0}'.format(client_id),
            return_type=Offer,
            method='DELETE'
        )

    def get_clients(self, **params):
        return self._api_call('clients/', params=params, return_type=Client)

    def export_clients(self, **params):
        return self._api_call('clients/', params=params, parse_json=False,
            headers={'Accept': 'text/csv'}
        )

    #
    # Offers
    #
    def new_offer(self, amount, name, interval='month', currency='EUR'):
        if amount == 0:
            return None
        if not RE_INT.search(str(amount)):
            raise ValueError('Amount is not an integer')
        if not RE_INTERVAL.search(interval):
            raise ValueError('Interval format: number DAY|WEEK|MONTH|YEAR Example: 2 DAY')

        return self._api_call('offers/',
            params={'amount': amount, 'interval': interval, 'currency': currency, 'name': name},
            return_type=Offer,
            method='POST'
        )

    def get_offer(self, offer_id):
        return self._api_call('offers/{0}'.format(offer_id), return_type=Offer)

    def update_offer(self, offer_id, name):
        return self._api_call('offers/{0}'.format(offer_id),
            params={'name': name},
            return_type=Offer,
            method='PUT'
        )

    def delete_offer(self, offer_id):
        return self._api_call('offers/{0}'.format(offer_id),
            return_type=Offer,
            method='DELETE'
        )

    def get_offers(self, **params):
        return self._api_call('offers/', params=params, return_type=Offer)

    #
    # Subscriptions
    #
    def new_subscription(self, client, offer, payment, start_at=None):
        params = {'start_at': start_at}

        if isinstance(start_at, (date, datetime)):
            params['start_at'] = re.sub(r'\..*$', '', str(time.mktime(start_at.timetuple())))

        params['client'] = isinstance(client, Client) and client.id or client
        params['offer'] = isinstance(offer, Offer) and offer.id or offer
        params['payment'] = isinstance(payment, Payment) and payment.id or payment

        return self._api_call('subscriptions/',
            params=params,
            return_type=Subscription,
            method='POST'
        )

    def get_subscription(self, subscription_id):
        return self._api_call('subscriptions/{0}'.format(subscription_id), return_type=Subscription)

    def update_subscription(self, subscription_id, offer):
        params = {
            'offer': isinstance(offer, Offer) and offer.id or offer
        }

        return self._api_call('subscriptions/{0}'.format(subscription_id),
            params=params,
            return_type=Subscription,
            method='PUT'
        )

    def cancel_subscription_after_interval(self, subscription_id, cancel=True):
        return self._api_call('subscriptions/{0}'.format(subscription_id),
            params={'cancel_at_period_end': cancel and 'true' or 'false'},
            return_type=Subscription,
            method='PUT'
        )

    def cancel_subscription_now(self, subscription_id):
        return self._api_call('subscriptions/{0}'.format(subscription_id),
            return_type=Subscription,
            method='DELETE'
        )

    def get_subscriptions(self, **params):
        return self._api_call('subscriptions/', params=params, return_type=Subscription)

    #
    # Webhooks
    #
    def new_webhook(self, event_types, url=None, email=None):
        if (url is None and email is None) or (url is not None and email is not None):
            raise ValueError('Please only provide url OR email.')

        return self._api_call('webhooks/',
            params={'url': url, 'email': email, 'event_types': event_types},
            return_type=Webhook,
            method='POST'
        )

    def get_webhook(self, webhook_id):
        return self._api_call('webhooks/{0}'.format(webhook_id), return_type=Webhook)

    def update_webhook(self, webhook_id, event_types=None, url=None, email=None):
        if url is not None and email is not None:
            raise ValueError('Please only provide url OR email.')

        return self._api_call('webhooks/{0}'.format(webhook_id),
            params={'url': url, 'email': email, 'event_types': event_types},
            return_type=Webhook,
            method='PUT'
        )

    def delete_webhook(self, webhook_id):
        return self._api_call('webhooks/{0}'.format(webhook_id),
            return_type=Webhook,
            method='DELETE'
        )

    def get_webhooks(self, **params):
        return self._api_call('webhooks/', params=params, return_type=Webhook)
