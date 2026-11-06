"""H13 regression tests, identity + zero structural categories + universe guardrails."""
import numpy as np
import pandas as pd
import pytest
from icml.sectoral.reconciliation import solve_joint_margins


def fixture():
    p=np.array([[0.15,0.35,0.5], [0.40,0.50,0.10], [0.32,0.21,0.47],
                [0.27,0.53,0.20], [0.18,0.45,0.37]])
    full=np.array([100.,130.,90.,190.,150.])
    geih=np.array([0.,130.,15.,180.,150.])
    q=np.array([0.30,0.42,0.28])
    return p,full,geih,q


def test_joint_geih_and_full_sector_margins_with_same_composition():
    p,f,g,q=fixture()
    x,m=solve_joint_margins(p,f,g,q,fit_geih=True)
    assert m['joint_geih']
    assert np.max(abs(x.sum(axis=1)-1))<1e-13
    assert np.max(abs((f@x)/f.sum()-q))<1e-10
    assert np.max(abs((g@x)/g.sum()-q))<1e-10
    assert np.max(abs(x-p))>0.001


def test_pre2001_geih_not_forced_to_dane_margin():
    p,f,g,q=fixture()
    x,m=solve_joint_margins(p,f,g,q,fit_geih=False)
    assert not m['joint_geih']
    assert np.max(abs(f@x/f.sum()-q))<1e-10
    assert np.max(abs(g@x/g.sum()-q))>1e-5


def test_neutral_prior_is_fixed_point():
    _,f,g,q=fixture()
    p=np.broadcast_to(q,(len(f),len(q))).copy()
    x,m=solve_joint_margins(p,f,g,q,fit_geih=True)
    assert np.allclose(x,p,atol=1e-12)
    assert m['iterations']==0


def test_zero_national_sector_is_structural_zero():
    p,f,g,q=fixture()
    p=np.c_[p,np.zeros(len(f))]
    q=np.r_[q,0.]
    x,_=solve_joint_margins(p,f,g,q,fit_geih=True)
    assert (x[:,-1]==0).all()
    assert np.allclose((f@x)/f.sum(),q,atol=1e-12)


def test_fail_fast_on_unsupported_sector_and_negative_values():
    p,f,g,q=fixture()
    wrong=p.copy();wrong[0,0]=0.;wrong[0,2]+=0.15
    with pytest.raises(ValueError,match='structural zero'):
        solve_joint_margins(wrong,f,g,q,fit_geih=True)
    with pytest.raises(ValueError,match='Negative'):
        solve_joint_margins(p,f,np.array([-1.,*g[1:]]),q,fit_geih=True)


def test_joint_is_kl_minimizer_against_feasible_perturbations():
    p,f,g,q=fixture()
    x,m=solve_joint_margins(p,f,g,q,fit_geih=True)
    # A feasible direction has zero departmental row sums and zero
    # national full/represented columns; we build a tangent direction.
    # One directional step should not reduce the convex KL objective.
    constraints=np.vstack([np.kron(np.eye(len(f)),np.ones((1,3))),
        np.kron(f.reshape(1,-1),np.eye(3)),np.kron(g.reshape(1,-1),np.eye(3))])
    u,s,vt=np.linalg.svd(constraints,full_matrices=True)
    rank=int(np.sum(s>1e-10))
    directions=vt[rank:].T
    assert directions.shape[1]>0
    z=directions[:,0].reshape(len(f),3)
    eps=1e-5
    def obj(t):return float(np.sum((f/f.sum())[:,None]*t*np.log(t/p)))
    assert obj(x+eps*z)>=obj(x)-1e-11
    assert obj(x-eps*z)>=obj(x)-1e-11
