"""No network or game input; persistent nine-cut contract."""
import tempfile
from pathlib import Path
import unittest
from core.netcut_budget import DisconnectBudget, MAX_CUTS
from core import log_reader


class BudgetTests(unittest.TestCase):
    def test_game_key_survives_process_restart_but_changes_with_new_game(self):
        original=log_reader.LOG_PATH
        try:
            log_reader.LOG_PATH='C:/synthetic/Power.log'
            line='D 12:00:00.0000000 GameState.DebugPrintPower() - CREATE_GAME\n'
            log_reader._reset();log_reader._parse_chunk([line])
            first=log_reader._current_game_key()
            log_reader._reset();log_reader._parse_chunk([line])
            self.assertEqual(first,log_reader._current_game_key())
            log_reader._parse_chunk([line.replace('12:00:00','12:20:00')])
            self.assertNotEqual(first,log_reader._current_game_key())
        finally:
            log_reader.LOG_PATH=original;log_reader._reset()

    def test_ninth_cut_allowed_and_tenth_blocked_across_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json';now=[1000.]
            def cut():return 1,'日志'
            budget=DisconnectBudget(path,clock=lambda:now[0],disconnect=cut)
            for turn in range(1,MAX_CUTS+1):
                now[0]+=20
                self.assertTrue(budget.cut('game','combat-'+str(turn))['ok'])
            restarted=DisconnectBudget(path,clock=lambda:now[0],disconnect=cut)
            now[0]+=20
            with self.assertRaisesRegex(RuntimeError,'9 次'):
                restarted.cut('game','combat-10')
            self.assertEqual(restarted.status('game')['remaining'],0)

    def test_new_game_has_fresh_budget_and_same_combat_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json';now=[1000.]
            budget=DisconnectBudget(path,clock=lambda:now[0],disconnect=lambda:(1,'日志'))
            budget.cut('game-a','combat-1')
            with self.assertRaisesRegex(RuntimeError,'已经拔过'):
                budget.cut('game-a','combat-1')
            self.assertEqual(budget.status('game-a')['count'],1)
            self.assertEqual(budget.status('game-b')['remaining'],9)

    def test_failed_disconnect_is_not_charged_and_cooldown_blocks_rapid_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json';now=[1000.]
            budget=DisconnectBudget(path,clock=lambda:now[0],disconnect=lambda:(0,'不在战斗中'))
            result=budget.cut('game','combat-1')
            self.assertFalse(result['ok']);self.assertEqual(result['count'],0)
            now[0]+=16
            budget._disconnect=lambda:(1,'日志')
            budget.cut('game','combat-1')
            with self.assertRaisesRegex(RuntimeError,'重连保护'):
                budget.cut('game','combat-2')


if __name__=='__main__':unittest.main()
