"""Native official ring semantics, without repairing source boundaries."""

import unittest

from shapely.geometry import shape

from firelens.arcgis_geometry import polygon_geojson

SHELL = [[-124, 49], [-124, 51], [-122, 51], [-122, 49], [-124, 49]]
HOLE = [[-123.8, 49.2], [-122.2, 49.2], [-122.2, 50.8], [-123.8, 50.8], [-123.8, 49.2]]


class NativeRingTests(unittest.TestCase):
    def test_hole_preceding_shell_keeps_exact_coordinates(self):
        result = polygon_geojson({"rings": [HOLE, SHELL]})
        self.assertEqual(result, {"type": "Polygon", "coordinates": [SHELL, HOLE]})
        self.assertTrue(shape(result).is_valid)
        self.assertAlmostEqual(shape(result).area, 4 - 1.6 * 1.6)

    def test_island_in_hole_remains_a_separate_polygon(self):
        island = [
            [-123.5, 49.5],
            [-123.5, 50.5],
            [-122.5, 50.5],
            [-122.5, 49.5],
            [-123.5, 49.5],
        ]
        result = polygon_geojson({"rings": [HOLE, island, SHELL]})
        self.assertEqual(result["type"], "MultiPolygon")
        self.assertTrue(shape(result).is_valid)

    def test_invalid_source_rings_are_not_repaired(self):
        invalid = [
            [],
            [SHELL[:-1]],
            [HOLE],
            [SHELL, SHELL],
            [[[-124, 49], [-122, 51], [-124, 51], [-122, 49], [-124, 49]]],
            [[[False, 49], [-124, 51], [-122, 51], [-122, 49], [False, 49]]],
            [[[1e300, 49], [-124, 51], [-122, 51], [-122, 49], [1e300, 49]]],
        ]
        for rings in invalid:
            with self.subTest(rings=rings), self.assertRaises(ValueError):
                polygon_geojson({"rings": rings})

    def test_no_coordinate_crs_or_curve_guessing(self):
        for extra in (
            {"spatialReference": {"wkid": 3857}},
            {"curveRings": [SHELL]},
            {"hasZ": True},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                polygon_geojson({"rings": [SHELL], **extra})
