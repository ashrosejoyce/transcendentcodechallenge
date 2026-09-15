import struct

from app.rag.visualization import _decode_vector, _project_to_2d


def _distance(p, q):
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def test_decode_vector_reads_little_endian_float32_blob():
    blob = struct.pack("<4f", 0.1, 0.2, 0.3, 0.4)
    decoded = _decode_vector(blob)
    assert len(decoded) == 4
    assert decoded[0] == struct.unpack("<f", struct.pack("<f", 0.1))[0]


def test_decode_vector_handles_empty_blob():
    assert _decode_vector(b"") == []


def test_project_to_2d_returns_one_point_per_input_vector():
    vectors = [[0.1, 0.2, 0.3, 0.4] * 24, [0.9, 0.8, 0.7, 0.6] * 24, [0.11, 0.19, 0.29, 0.41] * 24]
    points = _project_to_2d(vectors)
    assert points.shape == (3, 2)


def test_project_to_2d_similar_vectors_land_closer_than_dissimilar_ones():
    near_a = [0.1, 0.2, 0.3, 0.4] * 24
    near_b = [0.11, 0.19, 0.29, 0.41] * 24  # nearly identical to near_a
    far = [0.9, -0.8, 0.7, -0.6] * 24

    points = _project_to_2d([near_a, near_b, far])

    assert _distance(points[0], points[1]) < _distance(points[0], points[2])
