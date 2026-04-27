from __future__ import annotations


class LinearProductivityIPR:
    """
    Simple linear IPR model driven directly by productivity index J.

    The relation is:
        q = J * (p_res - p_wf)
    """

    def __init__(
        self,
        *,
        p_res_atma: float,
        productivity_index: float,
        p_test_atma: float,
        fw_perc: float = 0.0,
        pb_atma: float = -1.0,
    ) -> None:
        self.p_res_atma = float(p_res_atma)
        self.productivity_index = float(productivity_index)
        self.p_test_atma = float(p_test_atma)
        self.fw_perc = float(fw_perc)
        self.pb_atma = float(pb_atma)

    @property
    def pi_sm3day_atm(self) -> float:
        return self.productivity_index

    @property
    def q_test_sm3day(self) -> float:
        return self.calc_q_liq_sm3day(self.p_test_atma)

    def calc_q_liq_sm3day(self, p_wf_atma: float) -> float:
        if p_wf_atma >= self.p_res_atma:
            return 0.0
        return max(0.0, self.productivity_index * (self.p_res_atma - float(p_wf_atma)))

    def calc_p_wf_atma(self, q_liq_sm3day: float) -> float:
        if self.productivity_index <= 0:
            return self.p_res_atma
        p_wf_atma = self.p_res_atma - float(q_liq_sm3day) / self.productivity_index
        return max(0.0, min(self.p_res_atma, p_wf_atma))
