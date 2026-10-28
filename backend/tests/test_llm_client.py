import io
import json
import threading
import time
import unittest
import urllib.error
from unittest import mock

from application.adapters import llm

CFG = {"default_profile": "p", "profiles": {"p": {"base_url": "http://127.0.0.1:1/v1", "model": "m",
                                                  "max_concurrency": 4}}}
OK = {"choices": [{"message": {"content": "xin chào"}, "finish_reason": "stop"}], "usage": {"cost": 0.001}}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("http://x", code, "err", headers, io.BytesIO(b"busy"))


class Retries(unittest.TestCase):
    def call(self, effects):
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=effects) as up, \
                mock.patch.object(llm.time, "sleep") as sleep:
            try:
                return llm.chat("t", [{"role": "user", "content": "x"}], cfg=CFG), up, sleep
            except llm.LLMError as e:
                return e, up, sleep

    def test_overload_is_retried_with_backoff_and_retry_after(self):
        r, up, sleep = self.call([http_error(503), http_error(429, "7"), Response(json.dumps(OK).encode())])
        self.assertEqual((r.text, up.call_count), ("xin chào", 3))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2.0, 7.0])

    def test_bad_request_fails_at_once(self):
        r, up, sleep = self.call([http_error(400)])
        self.assertIsInstance(r, llm.LLMError)
        self.assertEqual((up.call_count, sleep.call_count), (1, 0))

    def test_gives_up_after_the_retries(self):
        r, up, _ = self.call([http_error(503)] * 4 + [TimeoutError()])
        self.assertIsInstance(r, llm.LLMError)
        self.assertEqual(up.call_count, 4)          # first try + 3 retries


class MapCalls(unittest.TestCase):
    def test_runs_side_by_side_and_keeps_order(self):
        live, peak, lock = [0], [0], threading.Lock()

        def slow(x):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            return x * 10

        with mock.patch.object(llm, "load_config", return_value=CFG):
            self.assertEqual(llm.concurrency("t"), 4)
            self.assertEqual(llm.map_calls("t", slow, list(range(8))), [x * 10 for x in range(8)])
        self.assertGreater(peak[0], 1)

    def test_one_at_a_time_by_default(self):
        cfg = {"default_profile": "p", "profiles": {"p": {"base_url": "http://127.0.0.1:1/v1"}}}
        with mock.patch.object(llm, "load_config", return_value=cfg):
            self.assertEqual(llm.concurrency("t"), 1)


if __name__ == "__main__":
    unittest.main()
