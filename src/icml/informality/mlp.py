"""Experimental, definition-specific residual MLP for informal-employment rates.

The backbone preserves the original notebook's architecture and *effective*
configuration; the Beta log-likelihood and training/early-stopping mechanics
are repaired. No city label is an observed monthly departmental outcome.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import math
import random
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError as exc:
    raise ImportError('The MLP experiment requires the optional dependency torch; install the ml extra (pip install -e ".[ml]").') from exc


@dataclass(frozen=True)
class MLPConfig:
    feature_cols: tuple[str, ...]
    hidden_dim: int = 128
    num_blocks: int = 1
    dropout: float = .1
    use_residual: bool = True
    loss_type: Literal['beta_nll','logit_huber','logit_mse'] = 'beta_nll'
    beta_phi: float = 20.
    huber_delta: float = 1.
    epochs: int = 160
    batch_size: int = 512
    lr: float = .001
    weight_decay: float = .001
    patience: int = 18
    min_delta: float = 1e-4
    seed: int = 42
    # Original alternatives are retained conceptually, but cannot be claimed
    # monotone: original LayerNorm and unconstrained head break that guarantee.
    monotonic_type: Literal['none'] = 'none'

    def __post_init__(self) -> None:
        if self.loss_type not in ('beta_nll','logit_huber','logit_mse'):
            raise ValueError('Unsupported loss')
        if self.monotonic_type != 'none':
            raise ValueError('Monotonic constraints cannot be guaranteed by original backbone')
        if not self.feature_cols or len(set(self.feature_cols))!=len(self.feature_cols):
            raise ValueError('Features missing or duplicated')
        if self.hidden_dim<=0 or self.num_blocks<0 or not (0<=self.dropout<1):
            raise ValueError('Invalid neural architecture')
        if self.beta_phi<=0 or self.epochs<1 or self.batch_size<1:
            raise ValueError('Invalid training parameters')


class ResidualBlock(nn.Module):
    """Exactly the residual transform of the original notebook."""
    def __init__(self, dim: int, dropout: float) -> None:
        super().__init__()
        self.norm=nn.LayerNorm(dim)
        self.linear=nn.Linear(dim,dim)
        self.dropout=nn.Dropout(dropout)
        self.act=nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.act(self.dropout(self.linear(self.norm(x))))


class MLPBackbone(nn.Module):
    """Original affine/ReLU/dropout + residual blocks + logit head."""
    def __init__(self, n_features: int, cfg: MLPConfig) -> None:
        super().__init__()
        seq: list[nn.Module]=[nn.Linear(n_features,cfg.hidden_dim),nn.ReLU(),nn.Dropout(cfg.dropout)]
        for _ in range(cfg.num_blocks):
            if cfg.use_residual:
                seq.append(ResidualBlock(cfg.hidden_dim,cfg.dropout))
            else:
                seq.extend([nn.Linear(cfg.hidden_dim,cfg.hidden_dim),nn.ReLU(),nn.Dropout(cfg.dropout)])
        seq.append(nn.Linear(cfg.hidden_dim,1))
        self.network=nn.Sequential(*seq)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x).squeeze(-1)


def beta_negative_log_likelihood(logits: torch.Tensor, y: torch.Tensor, phi: float) -> torch.Tensor:
    """FULL beta NLL including log B(alpha,beta), omitted by the notebook.

    Phi is fixed; this is a working density for estimated rates, NOT a claim
    that latent monthly rates are independent Beta-distributed observations.
    """
    yy=y.clamp(1e-6,1-1e-6)
    mu=torch.sigmoid(logits).clamp(1e-6,1-1e-6)
    alpha=(mu*phi).clamp_min(1e-5)
    beta=((1-mu)*phi).clamp_min(1e-5)
    log_norm=torch.lgamma(alpha)+torch.lgamma(beta)-torch.lgamma(alpha+beta)
    return (log_norm-(alpha-1)*torch.log(yy)-(beta-1)*torch.log1p(-yy)).mean()


def _loss(logits: torch.Tensor, y: torch.Tensor, cfg: MLPConfig) -> torch.Tensor:
    if cfg.loss_type=='beta_nll':
        return beta_negative_log_likelihood(logits,y,cfg.beta_phi)
    logits_y=torch.logit(y.clamp(1e-6,1-1e-6))
    if cfg.loss_type=='logit_huber':
        return F.huber_loss(logits,logits_y,delta=cfg.huber_delta)
    return F.mse_loss(logits,logits_y)


def group_p90_mape(y: np.ndarray, pred: np.ndarray, groups: np.ndarray) -> float:
    """Original evaluation preference: P90 of average MAPE by city."""
    frame=pd.DataFrame({'y':y,'pred':pred,'group':groups})
    frame['ape']=100*np.abs(frame.y-frame.pred)/np.maximum(np.abs(frame.y),1e-6)
    return float(np.percentile(frame.groupby('group',sort=True).ape.mean(),90))


def _seed(seed:int)->None:
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic=True
    torch.backends.cudnn.benchmark=False


class MLPInformality:
    def __init__(self,cfg:MLPConfig) -> None:
        self.cfg=cfg
        self.scaler: StandardScaler | None=None
        self.model: MLPBackbone | None=None
        self.history: list[dict[str,float]]=[]
        self.best_epoch: int=0
        self._fitted=False

    def _xy(self,df:pd.DataFrame, require_y:bool=True)->tuple[np.ndarray,np.ndarray | None]:
        missing=set(self.cfg.feature_cols)-set(df.columns)
        if missing:raise ValueError(f'Predictors missing: {sorted(missing)}')
        x=df[list(self.cfg.feature_cols)].to_numpy(dtype=np.float32)
        if not np.isfinite(x).all():raise ValueError('Imputation is forbidden: missing/nonfinite predictor')
        if not require_y:return x,None
        if 'target_latent_informal_rate' not in df:raise ValueError('Target is absent')
        y=df.target_latent_informal_rate.to_numpy(dtype=np.float32)
        if not np.isfinite(y).all() or np.any((y<0)|(y>1)):
            raise ValueError('Target must be finite rate in [0,1]')
        return x,y

    def fit(self,train:pd.DataFrame,val:pd.DataFrame|None=None,
            fixed_epochs:int|None=None)->'MLPInformality':
        _seed(self.cfg.seed)
        x,y=self._xy(train)
        self.scaler=StandardScaler().fit(x)
        xt=torch.from_numpy(self.scaler.transform(x).astype(np.float32))
        yt=torch.from_numpy(y)
        self.model=MLPBackbone(xt.shape[1],self.cfg)
        if val is not None:
            xv,yv=self._xy(val)
            vx=torch.from_numpy(self.scaler.transform(xv).astype(np.float32))
            vy=torch.from_numpy(yv)
            vg=val.dep_code.to_numpy()
        opt=torch.optim.Adam(self.model.parameters(),lr=self.cfg.lr,weight_decay=self.cfg.weight_decay)
        rng=torch.Generator().manual_seed(self.cfg.seed)
        dl=torch.utils.data.DataLoader(torch.utils.data.TensorDataset(xt,yt),
             batch_size=min(self.cfg.batch_size,len(train)),shuffle=True,generator=rng)
        limit=fixed_epochs if fixed_epochs is not None else self.cfg.epochs
        best=float('inf');best_state=None; stale=0
        self.history=[]
        for e in range(1,limit+1):
            self.model.train(); total=0.
            for xb,yb in dl:
                opt.zero_grad(set_to_none=True)
                out=self.model(xb)
                loss=_loss(out,yb,self.cfg)
                if not torch.isfinite(loss):raise FloatingPointError('Non-finite training loss')
                loss.backward();opt.step()
                total+=float(loss.detach())*len(xb)
            row={'epoch':float(e),'train_loss':total/len(train)}
            if val is not None:
                self.model.eval()
                with torch.no_grad():pred=torch.sigmoid(self.model(vx)).numpy()
                score=group_p90_mape(yv,pred,vg)
                row['inner_p90_mape']=score
                if score<best-self.cfg.min_delta:
                    best=score;self.best_epoch=e;stale=0
                    best_state=copy.deepcopy(self.model.state_dict())
                else:stale+=1
            self.history.append(row)
            if val is not None and stale>=self.cfg.patience:break
        if val is not None:
            if best_state is None:raise RuntimeError('Early stopping did not save any weights')
            self.model.load_state_dict(best_state)
        else:
            self.best_epoch=limit
        self.model.eval();self._fitted=True
        return self

    def predict(self,data:pd.DataFrame)->np.ndarray:
        if not self._fitted or self.scaler is None or self.model is None:
            raise RuntimeError('MLP is not fitted')
        x,_=self._xy(data,require_y=False)
        with torch.no_grad():
            p=torch.sigmoid(self.model(torch.from_numpy(self.scaler.transform(x).astype(np.float32)))).numpy()
        if not np.isfinite(p).all():raise FloatingPointError('Invalid MLP prediction')
        return np.clip(p.astype(np.float64),0,1)

    def metadata(self)->dict:
        return {'architecture':'notebook_residual_mlp','configuration':asdict(self.cfg),
                'best_epoch':self.best_epoch,'selection':'inner p90 city MAPE',
                'training_rows_type':'monthly latent estimated rates'}

    def export(self,folder)->None:
        from pathlib import Path
        import json
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        if not self._fitted or self.model is None or self.scaler is None:raise RuntimeError('Fit before export')
        torch.save(self.model.state_dict(),folder/'weights.pt')
        (folder/'configuration.json').write_text(json.dumps(self.metadata(),indent=2),encoding='utf8')
        (folder/'scaler.json').write_text(json.dumps({'mean':self.scaler.mean_.tolist(),
                     'scale':self.scaler.scale_.tolist(),'n_features':len(self.cfg.feature_cols)},indent=2),encoding='utf8')

    @classmethod
    def load(cls, folder) -> 'MLPInformality':
        """Reload state_dict only; never unpickle an arbitrary Python model."""
        from pathlib import Path
        import json
        folder = Path(folder)
        config = json.loads((folder / 'configuration.json').read_text(encoding='utf8'))
        cfg = config['configuration']
        cfg['feature_cols'] = tuple(cfg['feature_cols'])
        obj = cls(MLPConfig(**cfg))
        stats = json.loads((folder / 'scaler.json').read_text(encoding='utf8'))
        if stats['n_features'] != len(obj.cfg.feature_cols):
            raise ValueError('Saved scaler/feature count mismatch')
        obj.scaler = StandardScaler()
        obj.scaler.mean_ = np.asarray(stats['mean'], dtype=np.float64)
        obj.scaler.scale_ = np.asarray(stats['scale'], dtype=np.float64)
        obj.scaler.var_ = obj.scaler.scale_**2
        obj.scaler.n_features_in_ = len(obj.cfg.feature_cols)
        obj.model = MLPBackbone(len(obj.cfg.feature_cols), obj.cfg)
        obj.model.load_state_dict(torch.load(folder / 'weights.pt', map_location='cpu', weights_only=True))
        obj.model.eval()
        obj.best_epoch = int(config['best_epoch'])
        obj._fitted = True
        return obj
