class TakctlError(Exception):
    pass


class TakctlAssumptionError(TakctlError):
    pass


class TakctlNotFound(TakctlError):
    pass


class TakctlUnsafeOperation(TakctlError):
    pass

