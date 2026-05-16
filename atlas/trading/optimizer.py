from __future__ import annotations

from collections.abc import Callable

import optuna
import structlog

from atlas.trading.genome import Genome, GenomeFactory

log = structlog.get_logger()

optuna.logging.set_verbosity(optuna.logging.WARNING)


class OptunaStudy:
    """Wraps an Optuna study for genome optimization.

    storage=None uses in-memory storage (testing).
    Pass storage="postgresql+psycopg2://..." for production persistence.
    """

    def __init__(self, study_name: str, storage: str | None = None) -> None:
        self._study = optuna.create_study(
            study_name=study_name,
            storage=storage,
            direction="maximize",
            load_if_exists=True,
            sampler=optuna.samplers.TPESampler(
                seed=42
            ),  # seed: deterministic for CI reproducibility
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=0),
        )
        self._name = study_name

    def run_trials(
        self,
        n_trials: int,
        objective_fn: Callable[[Genome], float],
        n_jobs: int = 1,
    ) -> None:
        """Run n_trials Optuna trials. objective_fn receives a Genome, returns float.

        n_jobs controls thread-level parallelism. n_jobs=1 is sequential (the
        default and what the nightly cron uses). n_jobs>1 spawns Optuna's thread
        pool; each thread calls _wrapped → objective_fn → simulate_genome.

        Thread-safety notes for n_jobs>1:
          - list.append in the closure is atomic in CPython (no lock needed)
          - pandas pivot creates a new DataFrame per call (no shared mutation)
          - vectorbt's numba JIT cache is process-global; first thread compiles,
            others reuse. No per-thread warmup required.
          - Optuna's TPE sampler is thread-safe with the RDB storage backend.

        For c6i.8xlarge (32 vCPU) / c6i.16xlarge (64 vCPU) burn-in runs, set
        n_jobs to ~half the vCPU count to leave headroom for the OS + DB.
        """

        def _wrapped(trial: optuna.Trial) -> float:
            genome = GenomeFactory.from_optuna_trial(trial)
            return objective_fn(genome)

        try:
            self._study.optimize(
                _wrapped,
                n_trials=n_trials,
                n_jobs=n_jobs,
                show_progress_bar=False,
            )
        except Exception:
            log.exception("optuna_optimize_failed", study=self._name)
            raise
        log.info(
            "optuna_trials_complete",
            study=self._name,
            n_trials=len(self._study.trials),
            best_value=self._study.best_value,
            n_jobs=n_jobs,
        )

    def best_genome(self) -> Genome | None:
        """Return the Genome corresponding to the best trial, or None if no trials ran."""
        try:
            best_trial = self._study.best_trial
            return GenomeFactory.from_optuna_trial(optuna.trial.FixedTrial(best_trial.params))
        except RuntimeError:
            return None
        except Exception:
            log.warning("best_genome_unexpected_error", study=self._name)
            return None

    def get_parameter_importance(self) -> dict[str, float]:
        """Return parameter importance scores. Returns empty dict if insufficient trials."""
        try:
            return optuna.importance.get_param_importances(self._study)
        except ValueError:
            return {}
        except Exception:
            log.warning("param_importance_unexpected_error", study=self._name)
            return {}

    @classmethod
    def production(cls, db_url: str) -> OptunaStudy:
        """Create study backed by production Postgres DB."""
        storage = optuna.storages.RDBStorage(
            url=db_url,
            engine_kwargs={"pool_size": 5, "max_overflow": 10},
        )
        return cls(study_name="atlas_strategy_lab_v1", storage=storage)
