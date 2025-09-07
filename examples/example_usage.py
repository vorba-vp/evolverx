from evolverx.evolving import evolving, EvolverxConfig


@evolving(EvolverxConfig())
def add(x: float, y: float) -> float:
    """Return sum of two numbers."""
    raise NotImplementedError


@evolving(EvolverxConfig())
def divide(x: int, y: int) -> float:
    """Return division of x by y."""
    return x / y


if __name__ == "__main__":
    # Example usage of the add and divide function
    result = add(divide(4, 0), 2)
    print(result)
