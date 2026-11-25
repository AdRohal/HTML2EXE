import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import android_builder  # noqa: E402


def prereqs(java=True, sdk=True, node=True):
    def item(ok, msg):
        return {'ok': ok, 'message': msg if not ok else 'ok'}
    return {'java': item(java, 'Java not found'), 'sdk': item(sdk, 'Android SDK not found'),
            'node': item(node, 'Node.js not found'), 'allOk': java and sdk and node}


class AndroidGateTests(unittest.TestCase):
    def test_build_fails_fast_when_prerequisites_are_missing(self):
        builder = android_builder.AndroidBuilder()
        with mock.patch.object(android_builder.AndroidBuilder, 'check_prerequisites',
                               return_value=prereqs(java=False, sdk=False)), \
                mock.patch.object(android_builder.jobs, 'run') as run:
            result = builder.build({'projectId': 'x', 'appName': 'A', 'packageName': 'com.a.b'})
        self.assertFalse(result['success'])
        self.assertIn('Java not found', result['error'])
        self.assertIn('Android SDK not found', result['error'])
        self.assertIn('System Check', result['error'])
        run.assert_not_called()          # nothing was executed (no npm / Capacitor work)


if __name__ == '__main__':
    unittest.main()
