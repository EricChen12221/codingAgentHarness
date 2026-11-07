from calc import average
from mult import multiply

def test_average():
    assert average([2, 4, 6]) == 4

def test_multiply():
    assert multiply(3, 4) == 12
