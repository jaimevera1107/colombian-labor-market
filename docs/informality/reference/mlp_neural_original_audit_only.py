import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from dataclasses import dataclass

# =============================
# Numeric utilities
# =============================

def _set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def _safe_logit(y: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    y = np.clip(y, eps, 1.0 - eps)
    return np.log(y / (1.0 - y))

def _to_float_array(df, cols, dtype="float32") -> np.ndarray:
    block = df.loc[:, cols].apply(pd.to_numeric, errors="coerce").astype(dtype)
    return block.to_numpy(copy=False)

# =============================
# Model components
# =============================

class ResidualBlock(nn.Module):
    def __init__(self, dim: int, dropout: float):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.linear = nn.Linear(dim, dim)
        self.dropout = nn.Dropout(dropout)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm(x)
        h = self.linear(h)
        h = self.dropout(h)
        h = self.act(h)
        return x + h

class NonNegLinear(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, bias: bool = True):
        super().__init__()
        self.w_raw = nn.Parameter(torch.zeros(out_dim, in_dim))
        self.bias = nn.Parameter(torch.zeros(out_dim)) if bias else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        w = F.softplus(self.w_raw)
        out = x @ w.T
        if self.bias is not None:
            out = out + self.bias
        return out

class MonotonicFirstLayer(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, monotonic_mask: np.ndarray | None):
        super().__init__()
        if monotonic_mask is not None:
            m = torch.as_tensor(monotonic_mask.astype(np.float32))
            self.register_buffer("mask", m)
        else:
            self.mask = None
        self.w_raw = nn.Parameter(torch.zeros(out_dim, in_dim))
        self.b = nn.Parameter(torch.zeros(out_dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.mask is None:
            w = self.w_raw
        else:
            w = F.softplus(self.w_raw) * self.mask + self.w_raw * (1.0 - self.mask)
        return x @ w.T + self.b

class MonotonicResidualBlock(nn.Module):
    def __init__(self, dim: int, dropout: float):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.lin = NonNegLinear(dim, dim, bias=True)
        self.drop = nn.Dropout(dropout)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm(x)
        h = self.lin(h)
        h = self.drop(h)
        h = self.act(h)
        return x + h

# =============================
# Configuration
# =============================

@dataclass
class MLPConfig:
    """
    Configuration for MLPInformality.
    See previous message for full field docs.
    """
    feature_cols: list[str]
    target_col: str
    group_col: str

    hidden_dim: int = 128
    num_blocks: int = 2
    dropout: float = 0.10
    use_residual: bool = True

    monotonic_type: str = "none"          # "none" | "first_layer" | "all_layers"
    monotonic_mask: list[int] | None = None

    loss_type: str = "logit_huber"        # "logit_mse" | "logit_huber" | "beta_nll"
    huber_delta: float = 1.0
    beta_phi: float = 10.0

    epochs: int = 300
    batch_size: int = 512
    lr: float = 1e-3
    weight_decay: float = 1e-4
    grad_clip: float | None = None
    val_frac: float = 0.1
    patience: int = 20
    min_delta: float = 1e-4
    early_metric: str = "mape_p90"        # "val_loss_z" | "rmse_y" | "mae_y" | "mape_y" | "mape_p90"

    scaler_type: str = "standard"
    impute: bool = False
    float_dtype: str = "float32"

    temporal_val: bool = True
    enforce_output_bounds: bool = True

    stratified_year_seed: int | None = 42

    min_val_size: int = 64
    min_tr_size: int = 128

    seed: int = 42
    verbose: bool = False

# =============================
# Main model
# =============================

class MLPInformality:
    def __init__(self, config: MLPConfig):
        self.cfg = config
        _set_seed(config.seed)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        stype = config.scaler_type.lower()
        if stype == "standard":
            self._scaler_factory = lambda: StandardScaler()
        elif stype == "minmax":
            self._scaler_factory = lambda: MinMaxScaler()
        elif stype == "robust":
            self._scaler_factory = lambda: RobustScaler()
        else:
            raise ValueError("Invalid scaler_type.")

        self.model = None
        self.scaler = None
        self.imputer_stats_ = None

    # ---------- backbone ----------
    def _build_backbone(self, in_dim: int) -> nn.Module:
        cfg = self.cfg
        layers = []

        if cfg.monotonic_type == "first_layer":
            mask = np.array(cfg.monotonic_mask, dtype=np.float32) if cfg.monotonic_mask else None
            layers += [MonotonicFirstLayer(in_dim, cfg.hidden_dim, mask), nn.ReLU(), nn.Dropout(cfg.dropout)]
            for _ in range(cfg.num_blocks):
                if cfg.use_residual:
                    layers.append(ResidualBlock(cfg.hidden_dim, cfg.dropout))
                else:
                    layers += [nn.Linear(cfg.hidden_dim, cfg.hidden_dim), nn.ReLU(), nn.Dropout(cfg.dropout)]

        elif cfg.monotonic_type == "all_layers":
            layers += [NonNegLinear(in_dim, cfg.hidden_dim), nn.ReLU(), nn.Dropout(cfg.dropout)]
            for _ in range(cfg.num_blocks):
                if cfg.use_residual:
                    layers.append(MonotonicResidualBlock(cfg.hidden_dim, cfg.dropout))
                else:
                    layers += [NonNegLinear(cfg.hidden_dim, cfg.hidden_dim), nn.ReLU(), nn.Dropout(cfg.dropout)]

        else:  # none
            layers += [nn.Linear(in_dim, cfg.hidden_dim), nn.ReLU(), nn.Dropout(cfg.dropout)]
            for _ in range(cfg.num_blocks):
                if cfg.use_residual:
                    layers.append(ResidualBlock(cfg.hidden_dim, cfg.dropout))
                else:
                    layers += [nn.Linear(cfg.hidden_dim, cfg.hidden_dim), nn.ReLU(), nn.Dropout(cfg.dropout)]

        layers.append(nn.Linear(cfg.hidden_dim, 1))
        net = nn.Sequential(*layers)
        self._init_weights(net)
        return net.to(self.device)

    @staticmethod
    def _init_weights(module: nn.Module):
        for m in module.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_uniform_(m.weight, a=math.sqrt(5))
                if m.bias is not None:
                    fan_in, _ = nn.init._calculate_fan_in_and_fan_out(m.weight)
                    bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
                    nn.init.uniform_(m.bias, -bound, bound)

    # ---------- imputation ----------
    def _fit_imputer(self, X: np.ndarray):
        if not self.cfg.impute:
            self.imputer_stats_ = None
        else:
            self.imputer_stats_ = np.nanmedian(X, axis=0)

    def _apply_imputer(self, X: np.ndarray) -> np.ndarray:
        if self.imputer_stats_ is None:
            return X
        X = X.copy()
        inds = np.where(np.isnan(X))
        X[inds] = np.take(self.imputer_stats_, inds[1])
        return X

    # ---------- public API ----------
    def fit(self, df):
        X = _to_float_array(df, self.cfg.feature_cols, dtype=self.cfg.float_dtype)
        y = df[self.cfg.target_col].to_numpy().astype(self.cfg.float_dtype)
        self._fit_imputer(X)
        X = self._apply_imputer(X)
        self.scaler = self._scaler_factory()
        Xs = self.scaler.fit_transform(X).astype(self.cfg.float_dtype)
        self.model = self._build_backbone(Xs.shape[1])

        X_t = torch.from_numpy(Xs).to(self.device)
        y_t = torch.from_numpy(y.reshape(-1, 1)).to(self.device)

        if self.cfg.loss_type in ("logit_huber", "logit_mse"):
            Z_or_Y = torch.from_numpy(_safe_logit(y).reshape(-1, 1)).to(self.device)
        elif self.cfg.loss_type == "beta_nll":
            Z_or_Y = y_t
        else:
            raise ValueError("Unsupported loss_type.")

        # Training loop
        opt = torch.optim.Adam(self.model.parameters(), lr=self.cfg.lr, weight_decay=self.cfg.weight_decay)
        bs = min(self.cfg.batch_size, X_t.size(0))
        ds = torch.utils.data.TensorDataset(X_t, Z_or_Y)
        dl = torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=True)

        for epoch in range(self.cfg.epochs):
            self.model.train()
            for xb, tb in dl:
                opt.zero_grad()
                pred = self.model(xb)
                if self.cfg.loss_type == "logit_huber":
                    loss = F.huber_loss(pred, tb, delta=self.cfg.huber_delta)
                elif self.cfg.loss_type == "logit_mse":
                    loss = F.mse_loss(pred, tb)
                else:  # beta_nll
                    mu = torch.sigmoid(pred)
                    a = mu * self.cfg.beta_phi
                    b = (1 - mu) * self.cfg.beta_phi
                    log_beta_ab = torch.lgamma(a) + torch.lgamma(b) - torch.lgamma(a + b)
                    loss = -((a - 1)*torch.log(tb) + (b - 1)*torch.log(1 - tb) - log_beta_ab).mean()
                loss.backward()
                if self.cfg.grad_clip is not None:
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.cfg.grad_clip)
                opt.step()

    def predict(self, df):
        X = _to_float_array(df, self.cfg.feature_cols, dtype=self.cfg.float_dtype)
        X = self._apply_imputer(X)
        Xs = self.scaler.transform(X).astype(self.cfg.float_dtype)
        self.model.eval()
        with torch.no_grad():
            logits = self.model(torch.from_numpy(Xs).to(self.device))
            y_pred = torch.sigmoid(logits).cpu().numpy().reshape(-1)
        if self.cfg.enforce_output_bounds:
            y_pred = np.clip(y_pred, 0.0, 1.0)
        return y_pred