"""
Predictions_MX — Sistema de Predicción de Liga MX
Módulo predict: Dixon-Coles + Heurísticas del Analista + Bitácora
"""

from .features import get_team_form, get_full_feature_set, get_altitude_advantage
from .dixon_coles import fit_dixon_coles, predict_from_model
from .heuristics import apply_heuristics, detect_derby, load_manual_narratives
from .analyst_log import log_prediction, get_accuracy_report, recent_predictions
from .cli import generate_prediction, format_report, format_accuracy_report

__all__ = [
    'get_team_form', 'get_full_feature_set', 'get_altitude_advantage',
    'fit_dixon_coles', 'predict_from_model',
    'apply_heuristics', 'detect_derby', 'load_manual_narratives',
    'log_prediction', 'get_accuracy_report', 'recent_predictions',
    'generate_prediction', 'format_report', 'format_accuracy_report',
]
