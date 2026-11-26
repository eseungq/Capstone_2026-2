"""CPU selection/provenance checks, not GPU or TCP verification."""
import unittest
from ai_api.verify_integration import select_development_rows,inspection_id_for
import uuid

class IntegrationPreparation(unittest.TestCase):
    def test_new_http_case_ids_are_uuid_and_repeatable(self):
        a=inspection_id_for('run','good');b=inspection_id_for('run','defect')
        self.assertEqual(str(uuid.UUID(a)),a);self.assertNotEqual(a,b);self.assertEqual(a,inspection_id_for('run','good'))

    def test_internal_only_selection_and_boundary_cases(self):
        rows,selected,base=select_development_rows()
        self.assertEqual(len(rows),2039);self.assertEqual(len(selected),8)
        paths={r['image_path'] for r in rows};self.assertTrue({r['image_path'] for r in selected}<=paths)
        nearest={r['image_path'] for r in sorted(rows,key=lambda r:(abs(float(r['raw_defect_score'])-.5),r['image_path']))[:4]}
        self.assertTrue(nearest<={r['image_path'] for r in selected})
        self.assertEqual([int(r['predicted_class']) for r in base],[0,0,1,1])

if __name__=='__main__':unittest.main()
