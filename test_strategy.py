import unittest

from strategy_engine import new_state, process_spin


class TestRouletteStrategy(unittest.TestCase):

    def test_trigger_after_six_absences(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        self.assertTrue(state["dozens"]["1"]["active"])
        self.assertEqual(state["dozens"]["1"]["step"], 0)

    def test_zero_does_not_lose_bet(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        process_spin(0, state)

        item = state["dozens"]["1"]

        self.assertTrue(item["active"])
        self.assertEqual(item["step"], 0)
        self.assertEqual(item["losses"], 0)
        self.assertEqual(item["profit"], 0)

    def test_first_bet_win(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        process_spin(5, state)

        item = state["dozens"]["1"]

        self.assertFalse(item["active"])
        self.assertEqual(item["wins"], 1)
        self.assertEqual(item["profit"], 20)
        self.assertEqual(item["cycles_won"], 1)

    def test_four_consecutive_losses(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        for n in [20, 30, 20, 30]:
            process_spin(n, state)

        item = state["dozens"]["1"]

        self.assertFalse(item["active"])
        self.assertEqual(item["losses"], 4)
        self.assertEqual(item["cycles_lost"], 1)
        self.assertEqual(item["profit"], -85)

    def test_bet_progression(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        expected_steps = [1, 2, 3]

        for n, expected in zip([20, 30, 20], expected_steps):
            process_spin(n, state)
            self.assertEqual(
                state["dozens"]["1"]["step"],
                expected
            )

    def test_win_after_zero(self):
        state = new_state()

        for n in [13, 14, 15, 16, 17, 18]:
            process_spin(n, state)

        process_spin(0, state)
        process_spin(7, state)

        item = state["dozens"]["1"]

        self.assertFalse(item["active"])
        self.assertEqual(item["wins"], 1)
        self.assertEqual(item["profit"], 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
