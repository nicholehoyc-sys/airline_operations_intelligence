import unittest
import numpy as np
import pandas as pd
from airline_dea.dea_model import DEAModel
from airline_dea.ltm_pipeline import PeriodAnalyzer


class DEAModelTest(unittest.TestCase):
    def test_known_ccr_score_and_scale_invariance(self):
        x = pd.DataFrame({'fleet': [1., 2., 3.]}, index=['A','B','C'])
        y = pd.DataFrame({'flights': [2., 2., 2.]}, index=x.index)
        result = DEAModel(x, y).fit()
        self.assertAlmostEqual(result.efficiency['A'], 1.0)
        self.assertAlmostEqual(result.efficiency['B'], 0.5)
        self.assertAlmostEqual(result.efficiency['C'], 1/3)
        again = DEAModel(x * 1000, y * 0.001).fit()
        np.testing.assert_allclose(result.efficiency, again.efficiency, atol=1e-7)

    def test_nonradial_slack_does_not_collapse_to_zero(self):
        x = pd.DataFrame({'aircraft': [1., 1.], 'destinations': [1., 2.]}, index=['A','B'])
        y = pd.DataFrame({'flights': [1., 1.]}, index=x.index)
        result = DEAModel(x, y).fit()
        self.assertAlmostEqual(result.efficiency['B'], 1.)
        self.assertAlmostEqual(result.input_slacks.loc['B','destinations'], 1.)


    def test_pipeline_dea_slacks_remain_in_original_units(self):
        # B uses one unnecessary destination versus otherwise identical A.
        # The exported pipeline slack must be 1 destination, not a normalized 0.5.
        carriers = pd.DataFrame({
            "carrier": ["A", "B", "C"],
            "observed_aircraft": [1., 1., 2.],
            "distinct_destinations": [1., 2., 1.],
            "operated_flights": [100., 100., 150.],
            "on_time_arrivals": [90., 90., 135.],
        })
        ranking = PeriodAnalyzer._fit_dea(carriers).set_index("carrier")
        slack_text = ranking.loc["B", "input_slacks"]
        self.assertIn("distinct_destinations:1.00", slack_text)

    def test_invalid_inputs_rejected(self):
        x = pd.DataFrame({'input': [1., 0.]}, index=['A','B'])
        y = pd.DataFrame({'output': [1., 2.]}, index=['A','B'])
        with self.assertRaisesRegex(ValueError, 'positive inputs'):
            DEAModel(x,y)
        with self.assertRaisesRegex(ValueError, 'ordered DMU index'):
            DEAModel(x.iloc[::-1].assign(input=1.), y)
        with self.assertRaisesRegex(ValueError, 'finite'):
            DEAModel(x.assign(input=[1., np.nan]), y)
