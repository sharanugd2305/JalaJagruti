"""CNN-LSTM fusion network.

  CNN branch   : spatial land-surface context around the well
                 (NDVI, NDBI, log night lights, valid-pixel mask) -> embedding
  LSTM branch  : monthly sequence of groundwater level + climate forcing
  Fusion head  : [LSTM final hidden | CNN embedding] -> MLP -> delta
  Output       : next-month depth (z-score) = last observed depth_z + delta
"""
from __future__ import annotations

import torch
from torch import nn


class SpatialCNN(nn.Module):
    def __init__(self, in_ch: int = 4, emb: int = 32, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.AdaptiveAvgPool2d(1), nn.Flatten(),
            nn.Dropout(dropout), nn.Linear(64, emb), nn.ReLU())

    def forward(self, x):
        return self.net(x)


class TemporalLSTM(nn.Module):
    def __init__(self, n_features: int, hidden: int = 64, layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, num_layers=layers, batch_first=True,
                            dropout=dropout if layers > 1 else 0.0)

    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return h[-1]


class CNNLSTM(nn.Module):
    def __init__(self, n_seq_features: int, in_ch: int = 4, hidden: int = 64, layers: int = 2,
                 cnn_emb: int = 32, dropout: float = 0.2):
        super().__init__()
        self.cnn = SpatialCNN(in_ch, cnn_emb, dropout)
        self.lstm = TemporalLSTM(n_seq_features, hidden, layers, dropout)
        self.head = nn.Sequential(nn.Linear(hidden + cnn_emb, 64), nn.ReLU(), nn.Dropout(dropout),
                                  nn.Linear(64, 1))

    def forward(self, seq, patch):
        h = torch.cat([self.lstm(seq), self.cnn(patch)], dim=1)
        delta = self.head(h).squeeze(-1)
        return seq[:, -1, 0] + delta   # residual on last observed depth_z
