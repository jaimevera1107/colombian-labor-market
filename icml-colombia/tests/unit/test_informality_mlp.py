"""Regression tests for residual informal-rate network and repaired beta NLL."""
import numpy as np
import pandas as pd
import pytest

torch=pytest.importorskip('torch')
from scipy.stats import beta as scipy_beta
from icml.informality.mlp import (
    MLPConfig,MLPInformality,MLPBackbone,
    beta_negative_log_likelihood,group_p90_mape,
)


def test_beta_likelihood_includes_normalizing_constant():
    logits=torch.tensor([-1.2,0.0,1.3],requires_grad=True)
    y=torch.tensor([.20,.53,.81])
    phi=20.
    got=beta_negative_log_likelihood(logits,y,phi)
    mu=torch.sigmoid(logits).detach().numpy()
    expected=-np.mean(scipy_beta.logpdf(y.numpy(),a=mu*phi,b=(1-mu)*phi))
    assert np.isclose(float(got.detach()),expected,atol=2e-5)
    got.backward()
    assert torch.isfinite(logits.grad).all()


def test_beta_endpoints_finite():
    z=torch.tensor([0.0,1.0],requires_grad=True)
    y=torch.tensor([0.0,1.0])
    loss=beta_negative_log_likelihood(z,y,20)
    loss.backward()
    assert torch.isfinite(loss) and torch.isfinite(z.grad).all()


def test_original_architecture_shape_and_bounds():
    cfg=MLPConfig(feature_cols=('a','b'),epochs=5,hidden_dim=16,patience=3)
    net=MLPBackbone(2,cfg)
    assert any(type(m).__name__=='ResidualBlock' for m in net.modules())
    assert net(torch.zeros(4,2)).shape==(4,)
    df=pd.DataFrame({'a':np.linspace(-1,1,64),'b':np.linspace(0,2,64),
                    'target_latent_informal_rate':np.linspace(.3,.7,64),'dep_code':np.arange(64)%4})
    fit=MLPInformality(cfg).fit(df.iloc[:48],df.iloc[48:])
    pred=fit.predict(df)
    assert len(pred)==64 and np.isfinite(pred).all()
    assert (pred>=0).all() and (pred<=1).all()
    assert 1<=fit.best_epoch<=5
    assert all('inner_p90_mape' in x for x in fit.history)


def test_cannot_fit_missing_feature():
    cfg=MLPConfig(feature_cols=('does_not_exist',))
    with pytest.raises(ValueError,match='missing'):
        MLPInformality(cfg).fit(pd.DataFrame({'target_latent_informal_rate':[.5]}))


def test_cannot_enable_unproven_monotonicity():
    with pytest.raises(ValueError,match='Monotonic'):
        MLPConfig(feature_cols=('a',),monotonic_type='all_layers')


def test_mape_group_p90_expected():
    val=group_p90_mape(np.array([.5,.5,.2,.2]),np.array([.5,.4,.2,.3]),np.array([1,1,2,2]))
    assert 10<val<25


def test_export_and_safe_reload(tmp_path):
    cfg=MLPConfig(feature_cols=('a','b'),epochs=2,hidden_dim=8)
    df=pd.DataFrame({'a':np.linspace(-1,1,12),'b':np.linspace(0,1,12),
        'target_latent_informal_rate':np.linspace(.3,.6,12),'dep_code':[1]*12})
    original=MLPInformality(cfg).fit(df)
    original.export(tmp_path)
    loaded=MLPInformality.load(tmp_path)
    np.testing.assert_allclose(original.predict(df),loaded.predict(df),atol=1e-8)
