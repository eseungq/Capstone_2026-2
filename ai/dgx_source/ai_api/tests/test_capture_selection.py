import unittest
from ai_api.capture_selection import route

class CaptureTests(unittest.TestCase):
    def test_scope_and_visibility_are_not_quality(self):
        observation=dict(coverage='충족',readability='판독 가능',lighting='필요 표면 확인 가능',visibility224='둘 다 보임')
        scope=dict(type='door_outer_face',description='외측 도장면')
        self.assertEqual(route(None,scope),'NEEDS_REVIEW')
        self.assertEqual(route(observation,None),'HOLD_SCOPE_UNDEFINED')
        self.assertEqual(route(observation,scope),'PRIMARY_CAPTURE_CANDIDATE')
        self.assertEqual(route(dict(observation,visibility224='원본에만 보임'),scope),'HOLD_MODEL_INPUT_VISIBILITY')
        self.assertEqual(route(dict(observation,coverage='일부만 보임'),scope),'SUPPLEMENTARY_PARTIAL_VIEW')
        self.assertEqual(route(dict(observation,lighting='대부분 가림'),scope),'HOLD_CAPTURE_UNSUITABLE')

if __name__=='__main__':unittest.main()
