import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import people_removal as pr  # noqa: E402


def blank(w=100, h=60):
    return np.zeros((h, w), np.uint8)


class CombineMasksTests(unittest.TestCase):
    def test_people_on_a_sign_are_kept_as_part_of_the_sign(self):
        people, signs, vehicles = blank(), blank(), blank()
        people[10:20, 10:20] = 255  # a face on a billboard
        signs[5:25, 5:25] = 255
        people[40:50, 60:70] = 255  # a pedestrian on the street
        out = pr.combine_masks(people, signs, vehicles)
        self.assertEqual(out[15, 15], 0)
        self.assertEqual(out[45, 65], 255)

    def test_sign_margin_also_protects_the_sign_edge(self):
        people, signs = blank(), blank()
        signs[20:30, 20:30] = 255
        people[20:30, 31:33] = 255  # just outside the sign edge
        out = pr.combine_masks(people, signs, blank(), sign_margin=9)
        self.assertEqual(out[25, 31], 0)

    def test_vehicles_are_never_protected_by_signs_and_their_holes_are_filled(self):
        signs, vehicles = blank(), blank()
        vehicles[30:50, 10:50] = 255
        vehicles[35:45, 20:40] = 0  # SAM missed the wrap in the middle...
        signs[35:45, 20:40] = 255  # ...and read it as a screen
        out = pr.combine_masks(blank(), signs, vehicles)
        self.assertEqual(out[40, 30], 255)
        self.assertEqual(out[5, 5], 0)

    def test_a_vehicle_that_is_mostly_a_sign_is_a_billboard(self):
        signs, vehicles = blank(), blank()
        signs[30:58, 5:40] = 255
        vehicles[32:56, 8:38] = 255  # a curved billboard read as the side of a bus
        out = pr.combine_masks(blank(), signs, vehicles)
        self.assertEqual(out[40, 20], 0)

    def test_a_half_wrapped_car_is_still_removed(self):
        signs, vehicles = blank(), blank()
        vehicles[40:58, 10:50] = 255
        signs[40:58, 10:30] = 255  # the wrap is read as a screen
        out = pr.combine_masks(blank(), signs, vehicles)
        self.assertEqual(out[50, 40], 255)
        self.assertEqual(out[50, 20], 255)

    def test_a_vehicle_floating_in_the_upper_part_is_not_a_vehicle(self):
        vehicles = blank()
        vehicles[5:15, 60:90] = 255  # a light strip near the roofline
        vehicles[40:55, 10:30] = 255  # a car on the road
        out = pr.combine_masks(blank(), blank(), vehicles)
        self.assertEqual(out[10, 70], 0)
        self.assertEqual(out[45, 20], 255)

    def test_a_vehicle_reaching_the_sky_is_a_building(self):
        vehicles = blank()
        vehicles[2:58, 60:90] = 255  # a tower seen from below, read as the front of a bus
        out = pr.combine_masks(blank(), blank(), vehicles)
        self.assertEqual(out[40, 70], 0)

    def test_a_person_mostly_on_a_sign_is_dropped_with_its_fringe(self):
        people, signs = blank(), blank()
        signs[10:30, 10:40] = 255
        people[12:34, 12:38] = 255  # sign art read as a person, spilling below the sign
        people[40:55, 60:66] = 255  # a pedestrian
        out = pr.combine_masks(people, signs, blank(), sign_margin=3)
        self.assertEqual(out[32, 20], 0)
        self.assertEqual(out[45, 62], 255)

    def test_a_crowd_on_a_tower_read_as_a_bus_is_a_building(self):
        people, vehicles = blank(), blank()
        vehicles[0:58, 5:45] = 255  # a tower seen from below, read as the front of a bus...
        people[15:58, 8:42] = 255  # ...and its lower part as a crowd
        people[40:55, 60:66] = 255  # a pedestrian
        out = pr.combine_masks(people, blank(), vehicles)
        self.assertEqual(out[30, 20], 0)
        self.assertEqual(out[45, 62], 255)

    def test_a_close_person_reaching_the_top_is_still_removed(self):
        people = blank()
        people[0:58, 2:20] = 255  # a passer-by right in front of the camera
        out = pr.combine_masks(people, blank(), blank())
        self.assertEqual(out[30, 10], 255)

    def test_soft_inputs_are_thresholded(self):
        people = blank()
        people[0:5, 0:5] = 100  # below half: not a person
        people[10:15, 10:15] = 200
        out = pr.combine_masks(people, blank(), blank())
        self.assertEqual(out[2, 2], 0)
        self.assertEqual(out[12, 12], 255)


class GrowMaskTests(unittest.TestCase):
    def test_grow_size_is_odd_and_scales_with_the_image(self):
        self.assertEqual(pr.grow_size((100, 60)), 3)
        self.assertEqual(pr.grow_size((4000, 3000)), 49)
        self.assertEqual(pr.grow_size((4000, 3000)) % 2, 1)

    def test_grown_mask_reaches_past_the_original_and_is_soft(self):
        m = blank(2000, 300)  # grow size 25: about 12 px each side
        m[130:170, 180:220] = 255
        soft = np.asarray(pr.grow_mask(Image.fromarray(m)))
        self.assertEqual(soft[150, 200], 255)
        self.assertGreater(soft[150, 225], 127)  # trails beyond the edge are covered
        self.assertEqual(soft[10, 10], 0)
        self.assertTrue(((soft > 0) & (soft < 255)).any())


class ModelSizeTests(unittest.TestCase):
    def test_large_photos_are_scaled_to_max_side_in_multiples_of_8(self):
        self.assertEqual(pr.model_size((4000, 3000), 2048), (2048, 1536))
        w, h = pr.model_size((3001, 2001), 2048)
        self.assertEqual((w % 8, h % 8), (0, 0))
        self.assertLessEqual(max(w, h), 2048)

    def test_small_photos_are_not_upscaled(self):
        self.assertEqual(pr.model_size((1023, 767), 2048), (1016, 760))


class AddBoxesTests(unittest.TestCase):
    def test_boxes_in_fractions_of_the_photo_are_added_to_the_mask(self):
        m = np.zeros((100, 200), np.uint8)
        m[0:5, 0:5] = 255
        out = pr.add_boxes(m, [[0.5, 0.2, 0.6, 0.4]])
        self.assertEqual(out[30, 110], 255)
        self.assertEqual(out[30, 125], 0)
        self.assertEqual(out[2, 2], 255)  # the detected part stays
        self.assertEqual(m[30, 110], 0)  # input untouched

    def test_boxes_are_clipped_to_the_photo(self):
        out = pr.add_boxes(np.zeros((10, 10), np.uint8), [[0.9, 0.9, 1.5, 1.5]])
        self.assertEqual(out[9, 9], 255)
        self.assertEqual(int((out > 0).sum()), 1)

    def test_additions_for_a_photo_are_read_by_its_id(self):
        adds = {"044": [[0.4, 0.4, 0.5, 0.5]], "note": "ignored"}
        self.assertEqual(pr.boxes_for(adds, "044"), [[0.4, 0.4, 0.5, 0.5]])
        self.assertEqual(pr.boxes_for(adds, "117"), [])
        self.assertEqual(pr.boxes_for(None, "044"), [])

    def test_a_key_with_the_photo_folder_wins_over_the_bare_id(self):
        adds = {"139": [[0.5, 0.6, 0.9, 0.7]], "shibuya_centergai/139": [[0.1, 0.1, 0.2, 0.2]]}
        self.assertEqual(pr.boxes_for(adds, "139", "shibuya_centergai"), [[0.1, 0.1, 0.2, 0.2]])
        self.assertEqual(pr.boxes_for(adds, "139", "crossing_night"), [[0.5, 0.6, 0.9, 0.7]])


class SamSizeTests(unittest.TestCase):
    def test_photos_within_the_pixel_budget_are_sent_as_they_are(self):
        self.assertEqual(pr.sam_size((3840, 2560)), (3840, 2560))
        self.assertEqual(pr.sam_size((1024, 683)), (1024, 683))

    def test_a_tall_22_megapixel_photo_is_shrunk_to_the_budget_keeping_its_shape(self):
        w, h = pr.sam_size((3840, 5760))
        self.assertLessEqual(w * h, pr.SAM_MAX_PIXELS)
        self.assertGreater(w * h, 0.98 * pr.SAM_MAX_PIXELS)
        self.assertAlmostEqual(h / w, 1.5, places=2)


class CompositeTests(unittest.TestCase):
    def test_only_masked_pixels_change(self):
        photo = Image.new("RGB", (40, 20), (10, 20, 30))
        fill = Image.new("RGB", (40, 20), (200, 200, 200))
        mask = blank(40, 20)
        mask[:, 20:] = 255
        out = np.asarray(pr.composite(photo, fill, Image.fromarray(mask)))
        self.assertEqual(tuple(out[5, 5]), (10, 20, 30))
        self.assertEqual(tuple(out[5, 30]), (200, 200, 200))

    def test_fill_at_model_size_is_resized_back(self):
        photo = Image.new("RGB", (40, 20), (10, 20, 30))
        fill = Image.new("RGB", (16, 8), (200, 200, 200))
        out = pr.composite(photo, fill, Image.fromarray(np.full((20, 40), 255, np.uint8)))
        self.assertEqual(out.size, (40, 20))


class WorkflowTests(unittest.TestCase):
    def test_three_sam_passes_share_one_model_and_one_image(self):
        wf = pr.sam_workflow("in.png", people="person:300", signs="billboard:60", vehicles="car:30")
        detects = {k: v for k, v in wf.items() if v["class_type"] == "SAM3_Detect"}
        self.assertEqual(len(detects), 3)
        for node in detects.values():
            self.assertEqual(node["inputs"]["model"][0], node["inputs"]["model"][0])
            self.assertEqual(node["inputs"]["image"], ["2", 0])
        texts = sorted(v["inputs"]["text"] for v in wf.values() if v["class_type"] == "CLIPTextEncode")
        self.assertEqual(texts, ["billboard:60", "car:30", "person:300"])

    def test_each_pass_is_saved_under_its_output_node(self):
        wf = pr.sam_workflow("in.png")
        for key in pr.OUTPUT_NODES.values():
            self.assertEqual(wf[key]["class_type"], "SaveImage")

    def test_default_sign_prompt_does_not_match_wrapped_cars(self):
        self.assertNotIn("poster", pr.SIGN_PROMPT)
        self.assertNotIn("signboard", pr.SIGN_PROMPT)


if __name__ == "__main__":
    unittest.main()
