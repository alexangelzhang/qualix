"""Facade 等价性测试：旧命名 phase_[a-d] 应与新命名 phase_qXX 等价."""


class TestFacadeEquivalence:
    def test_phase_a_equivalent_to_phase_q01(self):
        from qualix.schemas import phase_a, phase_q01

        assert phase_a.PhaseAOutput is phase_q01.PhaseAOutput

    def test_phase_a3_equivalent_to_phase_q02(self):
        from qualix.schemas import phase_a3, phase_q02

        assert phase_a3.PhaseA3Output is phase_q02.PhaseA3Output

    def test_phase_a6_equivalent_to_phase_q03(self):
        from qualix.schemas import phase_a6, phase_q03

        assert phase_a6.PhaseA6Output is phase_q03.PhaseA6Output

    def test_phase_a5_equivalent_to_phase_q04(self):
        from qualix.schemas import phase_a5, phase_q04

        assert phase_a5.PhaseA5Output is phase_q04.PhaseA5Output

    def test_phase_b_equivalent_to_phase_q05(self):
        from qualix.schemas import phase_b, phase_q05

        assert phase_b.PhaseBOutput is phase_q05.PhaseBOutput
        assert phase_b.EutItem is phase_q05.EutItem
        assert phase_b.TCItem is phase_q05.TCItem

    def test_phase_c_equivalent_to_phase_q06(self):
        from qualix.schemas import phase_c, phase_q06

        assert phase_c.PhaseCOutput is phase_q06.PhaseCOutput
        assert phase_c.EutAuditItem is phase_q06.EutAuditItem
        assert phase_c.FindingItem is phase_q06.FindingItem

    def test_phase_d_equivalent_to_phase_q07(self):
        from qualix.schemas import phase_d, phase_q07

        assert phase_d.PhaseDOutput is phase_q07.PhaseDOutput


class TestOldImportPathsStillWork:
    def test_phase_b_import_still_works(self):
        from qualix.schemas.phase_b import EutItem, PhaseBOutput, TCItem

        assert EutItem.__name__ == "EutItem"
        assert TCItem.__name__ == "TCItem"
        assert PhaseBOutput.__name__ == "PhaseBOutput"

    def test_phase_c_import_still_works(self):
        from qualix.schemas.phase_c import EutAuditItem, FindingItem, PhaseCOutput

        assert EutAuditItem.__name__ == "EutAuditItem"
        assert FindingItem.__name__ == "FindingItem"
        assert PhaseCOutput.__name__ == "PhaseCOutput"
