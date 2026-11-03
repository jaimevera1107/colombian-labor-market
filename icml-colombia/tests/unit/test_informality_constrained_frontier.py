"""Accounting and option tests without any labels unavailable from DANE."""
from __future__ import annotations

import numpy as np
import pytest

from icml.informality.constrained_frontier import calibrate_quadratic, VARIANTS
from icml.informality.national_closure import calibrate_month, InfeasibleClosure

@pytest.mark.parametrize('variant',VARIANTS[1:])
def test_two_exact_constraints_fixed_employed(variant):
    p=np.array([.12,.31,.64,.88,.46]);e=np.array([100.,240.,80.,190.,150.]);f=np.array([0.,.3,1.,1.,.6])
    reference=np.array([.17,.34,.58,.81,.51])
    q=calibrate_quadratic(p,e,f,e@reference,(e*f)@reference,variant=variant,
         previous_correction=np.array([.01,-.02,.03,-.01,.02]))
    assert np.all((q>=0)&(q<=1))
    assert abs(e@q-e@reference)<1e-6
    assert abs((e*f)@q-(e*f)@reference)<1e-6
    assert np.max(np.abs(e*q+e*(1-q)-e))<1e-12

@pytest.mark.parametrize('variant',VARIANTS[1:])
def test_historical_single_constraint(variant):
    p=np.array([.2,.5,.65]);e=np.array([10.,20.,30.]);f=np.ones(3)
    q=calibrate_quadratic(p,e,f,27.,None,variant=variant)
    assert abs(e@q-27.)<1e-7

@pytest.mark.parametrize('variant',VARIANTS[1:])
def test_infeasible_targets_fail(variant):
    p=np.array([.4,.5,.6]);e=np.array([10.,10.,10.]);f=np.array([0.,0.,1.])
    with pytest.raises(InfeasibleClosure):
        calibrate_quadratic(p,e,f,5.,9.,variant=variant)


def test_original_kl_matches_locked_original():
    p=np.array([.2,.4,.7,.6]);e=np.array([100.,100.,100.,100.]);f=np.array([0.,.5,1.,1.])
    ref=calibrate_month(p,e,f,190.,130.)['calibrated_rate']
    assert np.all((ref>=0)&(ref<=1))
    assert abs(e@ref-190.)<1e-5


def test_temporal_requires_matching_prior_correction():
    with pytest.raises(ValueError):
        calibrate_quadratic(np.array([.3,.5]),np.array([10.,10.]),np.array([0.,1.]),10.,5.,
                            variant='l2_temporal_4',previous_correction=np.array([.1]))
