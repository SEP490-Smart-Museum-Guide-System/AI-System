import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.schemas import Candidate, PlanRequest
from app.engine import recommend
from app.main import app


def candidate(i, name, topic, gallery=1, floor=1, minutes=5):
    return Candidate(artifact_id=i, content_version_id=100+i, museum_id=1, name=name, title=name,
        description=name, topics=[topic], gallery_id=gallery, floor_id=floor, gallery_name=f"Phòng {gallery}", visit_minutes=minutes)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [candidate(1, "Bình gốm hoa nâu", "Gốm sứ"), candidate(2, "Bát men gốm", "Gốm sứ"),
                           candidate(3, "Trống đồng", "Đồ đồng", 2), candidate(4, "Thạp đồng", "Đồ đồng", 2)]

    def request(self, interests=None, minutes=30, candidates=None):
        return PlanRequest(museum_id=1, available_minutes=minutes, interests=interests or ["Gốm sứ"], candidates=candidates or self.candidates)

    def test_interests_change_actual_stops(self):
        pottery = recommend(self.request())
        bronze = recommend(self.request(["Đồ đồng"]))
        self.assertEqual({s.artifact_id for s in pottery.stops}, {1, 2})
        self.assertEqual({s.artifact_id for s in bronze.stops}, {3, 4})
        self.assertFalse(pottery.used_fallback)

    def test_budget_and_unique_ids_including_orientation(self):
        plan = recommend(self.request(minutes=10))
        self.assertEqual(len(plan.stops), 1)
        self.assertLessEqual(plan.estimated_minutes, 10)
        self.assertEqual(plan.estimated_minutes, sum(s.walk_minutes+s.visit_minutes for s in plan.stops))
        self.assertEqual(plan.stops[0].walk_minutes, 2)

    def test_long_descriptions_do_not_dilute_relevant_titles(self):
        pottery = candidate(1, "Đầu rồng đất nung thời Lý", "Gốm sứ cổ").model_copy(update={"topics": [], "description": "lưu giữ dấu vết trưng bày " * 100})
        bronze = candidate(2, "Trống đồng Ngọc Lũ", "Văn hóa Đông Sơn").model_copy(update={"topics": [], "description": "lưu giữ dấu vết trưng bày " * 100})
        self.assertEqual([s.artifact_id for s in recommend(self.request(["Gốm sứ"], candidates=[pottery, bronze])).stops], [1])
        self.assertEqual([s.artifact_id for s in recommend(self.request(["Đồ đồng"], candidates=[pottery, bronze])).stops], [2])

    def test_no_room_in_budget_is_explicit(self):
        plan = recommend(self.request(minutes=5))
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.estimated_minutes, 0)
        self.assertIn("chưa đủ", plan.notice)

    def test_unknown_interest_is_labelled_fallback(self):
        result = recommend(self.request(["Thiên thạch sao Hỏa"]))
        self.assertTrue(result.used_fallback)
        self.assertTrue(all(not s.matched_interests for s in result.stops))
        self.assertIn("thay thế", result.notice)

    def test_room_clustering_and_repeatability(self):
        request = self.request(["Gốm sứ", "Đồ đồng"])
        self.assertEqual(recommend(request), recommend(request))
        plan = recommend(request)
        self.assertEqual(plan.stops[1].walk_minutes, 0.5)

    def test_invalid_candidate_identity_and_budget(self):
        foreign = self.candidates[0].model_copy(update={"museum_id": 2})
        for values in ([foreign], [self.candidates[0], self.candidates[0]]):
            with self.assertRaises(ValidationError):
                self.request(candidates=values)
        with self.assertRaises(ValidationError): self.request(minutes=0)

    def test_internal_api_requires_key_and_preserves_contract(self):
        with patch.dict(os.environ, {"AI_TOUR_SERVICE_KEY": "t"*40}):
            with TestClient(app) as client:
                payload = self.request().model_dump(by_alias=True)
                self.assertEqual(client.post('/api/v1/tours/recommend', json=payload).status_code, 401)
                response = client.post('/api/v1/tours/recommend', json=payload, headers={"X-Service-Key": "t"*40})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['engineVersion'], 'content-tfidf-v1')
                self.assertTrue(response.json()['stops'])

    def test_unconfigured_service_is_not_ready(self):
        with patch.dict(os.environ, {"AI_TOUR_SERVICE_KEY": ""}):
            with TestClient(app) as client:
                self.assertEqual(client.get('/ready').status_code, 503)


if __name__ == '__main__': unittest.main()
