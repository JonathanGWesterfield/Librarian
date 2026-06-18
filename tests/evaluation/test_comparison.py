import unittest

from librarian_evaluation.comparison import compare_report_documents


class EvaluationComparisonTests(unittest.TestCase):
    def test_compare_report_documents_marks_metric_deltas(self) -> None:
        """Verify report comparisons classify improvements and regressions.
        Retrieval and answer scores are better when they increase, while
        latency is better when it decreases. This gives PR reports an
        automatic before/after summary instead of only showing raw metrics.
        """
        baseline = _report(
            overall_score=0.5,
            hit_rate=0.6,
            precision=0.4,
            recall=0.5,
            mrr=0.5,
            answer_score=0.7,
            elapsed_seconds=2.0,
        )
        current = _report(
            overall_score=0.6,
            hit_rate=0.6,
            precision=0.3,
            recall=0.7,
            mrr=0.6,
            answer_score=0.8,
            elapsed_seconds=1.5,
        )

        comparison = compare_report_documents(
            current,
            baseline,
            baseline_label="main",
        )

        self.assertEqual(comparison["baseline"], "main")
        self.assertEqual(comparison["improved_count"], 10)
        self.assertEqual(comparison["regressed_count"], 1)
        self.assertEqual(comparison["unchanged_count"], 1)
        metrics_by_name = {
            metric["name"]: metric for metric in comparison["metrics"]
        }
        self.assertEqual(metrics_by_name["overall_score"]["delta"], 0.1)
        self.assertEqual(metrics_by_name["precision_at_5"]["status"], "regressed")
        self.assertEqual(metrics_by_name["elapsed_seconds"]["status"], "improved")


def _report(
    *,
    overall_score: float,
    hit_rate: float,
    precision: float,
    recall: float,
    mrr: float,
    answer_score: float,
    elapsed_seconds: float,
) -> dict:
    return {
        "benchmark": {"name": "unit"},
        "summary": {
            "primary_k": 5,
            "overall_score": overall_score,
            "key_metrics": {
                "hit_rate_at_k": hit_rate,
                "mean_precision_at_k": precision,
                "mean_recall_at_k": recall,
                "mean_reciprocal_rank": mrr,
            },
        },
        "answer_quality": {
            "aggregate": {
                "mean_overall_score": answer_score,
                "mean_correctness": answer_score,
                "mean_groundedness": answer_score,
                "mean_citation_accuracy": answer_score,
                "mean_refusal_quality": answer_score,
                "mean_usefulness": answer_score,
            }
        },
        "run": {
            "execution": {"elapsed_seconds": elapsed_seconds},
            "git": {"short_commit": "abc1234", "branch": "test"},
        },
    }


if __name__ == "__main__":
    unittest.main()
