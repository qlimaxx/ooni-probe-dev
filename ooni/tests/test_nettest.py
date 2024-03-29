import os
from StringIO import StringIO
from tempfile import TemporaryFile, mkstemp

from twisted.trial import unittest
from twisted.internet import defer, reactor
from twisted.python.usage import UsageError

from ooni.settings import config
from ooni.errors import MissingRequiredOption, InvalidOption, FailureToLoadNetTest
from ooni.nettest import NetTest, NetTestLoader
from ooni.tasks import BaseTask

from ooni.director import Director
from ooni.managers import TaskManager

from ooni.tests.mocks import MockMeasurement, MockMeasurementFailOnce
from ooni.tests.mocks import MockNetTest, MockDirector, MockReporter
from ooni.tests.mocks import MockMeasurementManager
defer.setDebugging(True)

net_test_string = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCase(NetTestCase):

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'
"""

net_test_root_required = net_test_string+"""
    requiresRoot = True
"""

net_test_string_with_file = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCase(NetTestCase):
    inputFile = ['file', 'f', None, 'The input File']

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'
"""

net_test_string_with_required_option = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham'],
                     ['foo', 'o', None, 'moo'],
                     ['bar', 'o', None, 'baz'],
    ]

class DummyTestCase(NetTestCase):
    inputFile = ['file', 'f', None, 'The input File']

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'

    requiredOptions = ['foo', 'bar']
"""

http_net_test = """
from twisted.internet import defer
from twisted.python import usage, failure

from ooni.utils import log
from ooni.utils.net import userAgents
from ooni.templates import httpt
from ooni.errors import failureToString, handleAllFailures

class UsageOptions(usage.Options):
    optParameters = [
                     ['url', 'u', None, 'Specify a single URL to test.'],
                     ['factor', 'f', 0.8, 'What factor should be used for triggering censorship (0.8 == 80%)']
                    ]

class HTTPBasedTest(httpt.HTTPTest):
    usageOptions = UsageOptions
    def test_get(self):
        return self.doRequest(self.localOptions['url'], method="GET",
                              use_tor=False)
"""

dummyInputs = range(1)
dummyArgs = ('--spam', 'notham')
dummyOptions = {'spam':'notham'}
dummyInvalidArgs = ('--cram', 'jam')
dummyInvalidOptions= {'cram':'jam'}
dummyArgsWithRequiredOptions = ('--foo', 'moo', '--bar', 'baz')
dummyRequiredOptions = {'foo':'moo', 'bar':'baz'}
dummyArgsWithFile = ('--spam', 'notham', '--file', 'dummyInputFile.txt')

class TestNetTest(unittest.TestCase):
    timeout = 1
    def setUp(self):
        with open('dummyInputFile.txt', 'w') as f:
            for i in range(10):
                f.write("%s\n" % i)

        from ooni.settings import config
        config.read_config_file()

    def assertCallable(self, thing):
        self.assertIn('__call__', dir(thing))

    def verifyMethods(self, testCases):
        uniq_test_methods = set()
        for test_class, test_methods in testCases:
            instance = test_class()
            for test_method in test_methods:
                c = getattr(instance, test_method)
                self.assertCallable(c)
                uniq_test_methods.add(test_method)
        self.assertEqual(set(['test_a', 'test_b']), uniq_test_methods)

    def test_load_net_test_from_file(self):
        """
        Given a file verify that the net test cases are properly
        generated.
        """
        __, net_test_file = mkstemp()
        with open(net_test_file, 'w') as f:
            f.write(net_test_string)
        f.close()

        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestFile(net_test_file)

        self.verifyMethods(ntl.testCases)
        os.unlink(net_test_file)

    def test_load_net_test_from_str(self):
        """
        Given a file like object verify that the net test cases are properly
        generated.
        """
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        self.verifyMethods(ntl.testCases)

    def test_load_net_test_from_StringIO(self):
        """
        Given a file like object verify that the net test cases are properly
        generated.
        """
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        self.verifyMethods(ntl.testCases)

    def test_load_with_option(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        self.assertIsInstance(ntl, NetTestLoader)
        for test_klass, test_meth in ntl.testCases:
            for option in dummyOptions.keys():
                self.assertIn(option, test_klass.usageOptions())

    def test_load_with_invalid_option(self):
        try:
            ntl = NetTestLoader(dummyInvalidArgs)
            ntl.loadNetTestString(net_test_string)

            ntl.checkOptions()
            raise Exception
        except UsageError:
            pass

    def test_load_with_required_option(self):
        ntl = NetTestLoader(dummyArgsWithRequiredOptions)
        ntl.loadNetTestString(net_test_string_with_required_option)

        self.assertIsInstance(ntl, NetTestLoader)

    def test_load_with_missing_required_option(self):
        try:
            ntl = NetTestLoader(dummyArgs)
            ntl.loadNetTestString(net_test_string_with_required_option)

        except MissingRequiredOption:
            pass

    def test_net_test_inputs(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)

        ntl.checkOptions()
        nt = NetTest(ntl,None)
        nt.initializeInputProcessor()

        # XXX: if you use the same test_class twice you will have consumed all
        # of its inputs!
        tested = set([])
        for test_class, test_method in ntl.testCases:
            if test_class not in tested:
                tested.update([test_class])
                self.assertEqual(len(list(test_class.inputs)), 10)

    def test_setup_local_options_in_test_cases(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        ntl.checkOptions()

        for test_class, test_method in ntl.testCases:
            self.assertEqual(test_class.localOptions, dummyOptions)

    def test_generate_measurements_size(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)

        ntl.checkOptions()
        net_test = NetTest(ntl, None)

        net_test.initializeInputProcessor()
        measurements = list(net_test.generateMeasurements())
        self.assertEqual(len(measurements), 20)

    def test_net_test_completed_callback(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)

        ntl.checkOptions()
        director = Director()

        d = director.startNetTest(ntl, [MockReporter()])

        @d.addCallback
        def complete(result):
            self.assertEqual(result, None)
            self.assertEqual(director.successfulMeasurements, 20)

        return d

    def test_require_root_succeed(self):
        #XXX: will require root to run
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_root_required)

        for test_class, method in ntl.testCases:
            self.assertTrue(test_class.requiresRoot)

class TestNettestTimeout(unittest.TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        from twisted.internet.protocol import Protocol, Factory
        from twisted.internet.endpoints import TCP4ServerEndpoint

        class DummyProtocol(Protocol):
            def dataReceived(self, data):
                pass

        class DummyFactory(Factory):
            def __init__(self):
                self.protocols = []

            def buildProtocol(self, addr):
                proto = DummyProtocol()
                self.protocols.append(proto)
                return proto

            def stopFactory(self):
                for proto in self.protocols:
                    proto.transport.loseConnection()

        self.factory = DummyFactory()
        endpoint = TCP4ServerEndpoint(reactor, 8007)
        self.port = yield endpoint.listen(self.factory)

        config.advanced.measurement_timeout = 2

    def tearDown(self):
        self.factory.stopFactory()
        self.port.stopListening()
    
    def test_nettest_timeout(self):
        ntl = NetTestLoader(('-u', 'http://localhost:8007/'))
        ntl.loadNetTestString(http_net_test)

        ntl.checkOptions()
        director = Director()

        d = director.startNetTest(ntl, [MockReporter()])

        @d.addCallback
        def complete(result):
            assert director.failedMeasurements == 1

        return d
