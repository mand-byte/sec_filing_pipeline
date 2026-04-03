from enum import Enum, auto


class RouteType(str, Enum):
    ISSUER = "ISSUER"
    OWNER = "OWNER"
    HOLDINGS = "HOLDINGS"


class FormType(str, Enum):
    # Issuer Route
    F_10K = "10-K"
    F_10KA = "10-K/A"
    F_10Q = "10-Q"
    F_10QA = "10-Q/A"
    F_8K = "8-K"
    F_8KA = "8-K/A"
    F_20F = "20-F"
    F_20FA = "20-F/A"
    F_S1 = "S-1"
    F_S1A = "S-1/A"
    
    # Owner Route
    F_3 = "3"
    F_3A = "3/A"
    F_4 = "4"
    F_4A = "4/A"
    F_5 = "5"
    F_5A = "5/A"
    F_13D = "13D"
    F_13DA = "13D/A"
    F_13G = "13G"
    F_13GA = "13G/A"
    
    # Holdings Route
    F_13FHR = "13F-HR"
    F_13FHRA = "13F-HR/A"
    
    # Fallback or Raw
    OTHER = "OTHER"
    
    @property
    def is_amendment(self) -> bool:
        return self.value.endswith("/A")
