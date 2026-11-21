import unittest
import numpy as np
from app.engine import decoder_token


class DecoderTests(unittest.TestCase):
    def test_chat_default_stays_greedy_and_can_finish_immediately(self):
        self.assertEqual(decoder_token(np.array([1., 5., 3.]), [], {1}), 1)

    def test_narration_minimum_blocks_eos_only_until_requested_length(self):
        scores = np.array([1., 5., 3.])
        self.assertEqual(decoder_token(scores, [], {1}, min_new_tokens=2), 2)
        self.assertEqual(decoder_token(scores, [0, 2], {1}, min_new_tokens=2), 1)
        np.testing.assert_array_equal(scores, [1., 5., 3.])

    def test_penalty_discourages_repeating_a_generated_token(self):
        self.assertEqual(decoder_token(np.array([4., 3., 1.]), [0], {2}, repetition_penalty=2), 1)

    def test_seeded_sampling_is_reproducible_and_never_selects_masked_eos(self):
        def sample():
            rng = np.random.default_rng(17)
            return [decoder_token(np.array([1., 1.1, 10.]), [], {2}, min_new_tokens=2,
                                  temperature=.5, rng=rng) for _ in range(30)]
        result = sample()
        self.assertEqual(result, sample())
        self.assertEqual(set(result), {0, 1})
