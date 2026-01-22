"""
MicroDollar value object for type-safe integer-based currency operations.

Standard: $1.00 = 1,000,000 micro-credits
This allows representing prices like $0.0015 as 1,500 integers.

Usage:
    # Create from int (e.g., from database value)
    balance = MicroDollar(user.credits_balance)
    
    # Calculations
    cost = MicroDollar(1500) * 10  # 10 pages @ $0.0015/page
    
    # Get raw int value (e.g., for database storage)
    user.credits_balance = cost.amount
    
    # To frontend display
    display_credits = cost.to_ui_string()  # Returns int for display
"""
from decimal import Decimal


class MicroDollar:
    """
    Value object representing currency in micro-units (1/1,000,000 of a dollar).
    
    All arithmetic is integer-based to prevent floating-point errors in billing.
    
    Example:
        price = MicroDollar(1_500)  # $0.0015
        total = price * 10          # 10 pages -> 15,000 micros ($0.015)
    """
    SCALE = 1_000_000  # $1.00 = 1,000,000 micros

    def __init__(self, micro_credits: int):
        """
        Initialize with an integer amount in micro-credits.
        
        Args:
            micro_credits: Integer value in micro-units (1/1,000,000 of a dollar)
            
        Raises:
            TypeError: If micro_credits is not an integer
        """
        if not isinstance(micro_credits, int):
            raise TypeError(
                f"MicroDollar must be initialized with an integer, got {type(micro_credits).__name__}"
            )
        self._amount = micro_credits

    @property
    def amount(self) -> int:
        """The raw micro-credit value."""
        return self._amount

    # =============================================
    # Factory Methods
    # =============================================

    # shoud we call this from_credits? 
    @classmethod
    def from_dollars(cls, amount: int) -> "MicroDollar":
        """
        Convert a dollar amount to MicroDollar.
        
        Args:
            amount: Dollar amount as int (e.g., 1 for $1.00)
            
        Returns:
            MicroDollar instance
            
        Example:
            MicroDollar.from_dollars(1) -> MicroDollar(1_000_000)
        """
        return cls(amount * cls.SCALE)

    @classmethod
    def from_float(cls, amount: float) -> "MicroDollar":
        """
        Convert a float dollar amount to MicroDollar.
        
        WARNING: Use only for user input conversion. Internal calculations
        should use integer arithmetic exclusively.
        
        Args:
            amount: Dollar amount as float (e.g., 0.0015 for $0.0015)
            
        Returns:
            MicroDollar instance
            
        Example:
            MicroDollar.from_float(0.0015) -> MicroDollar(1500)
        """
        d = Decimal(str(amount))
        micros = int(d * cls.SCALE)
        return cls(micros)

    @classmethod
    def from_cents(cls, cents: int) -> "MicroDollar":
        """
        Convert cents to MicroDollar.
        
        Args:
            cents: Amount in cents (100 cents = $1.00)
            
        Returns:
            MicroDollar instance
            
        Example:
            MicroDollar.from_cents(150) -> MicroDollar(1_500_000) = $1.50
        """
        if not isinstance(cents, int):
            raise TypeError(f"Cents must be an integer, got {type(cents).__name__}")
        return cls(cents * 10_000)  # 1 cent = 10,000 micros

    @classmethod
    def zero(cls) -> "MicroDollar":
        """Return a zero-value MicroDollar."""
        return cls(0)

    # =============================================
    # Arithmetic Operations
    # =============================================

    def __add__(self, other: "MicroDollar") -> "MicroDollar":
        """Add two MicroDollar values."""
        if not isinstance(other, MicroDollar):
            raise TypeError(f"Cannot add MicroDollar with {type(other).__name__}")
        return MicroDollar(self._amount + other._amount)

    def __sub__(self, other: "MicroDollar") -> "MicroDollar":
        """Subtract two MicroDollar values."""
        if not isinstance(other, MicroDollar):
            raise TypeError(f"Cannot subtract MicroDollar with {type(other).__name__}")
        return MicroDollar(self._amount - other._amount)

    def __mul__(self, quantity: int) -> "MicroDollar":
        """
        Multiply by a scalar quantity (integer only).
        
        Example: 10 pages * $0.0015/page = $0.015
        """
        if not isinstance(quantity, int):
            raise TypeError(
                f"MicroDollar can only be multiplied by an integer, got {type(quantity).__name__}"
            )
        return MicroDollar(self._amount * quantity)

    def __rmul__(self, quantity: int) -> "MicroDollar":
        """Support quantity * MicroDollar syntax."""
        return self.__mul__(quantity)

    def __floordiv__(self, divisor: int) -> "MicroDollar":
        """Integer division by a scalar."""
        if not isinstance(divisor, int):
            raise TypeError(
                f"MicroDollar can only be divided by an integer, got {type(divisor).__name__}"
            )
        return MicroDollar(self._amount // divisor)

    def __neg__(self) -> "MicroDollar":
        """Negate the value (for deductions)."""
        return MicroDollar(-self._amount)

    # =============================================
    # Comparison Operations
    # =============================================

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MicroDollar):
            return NotImplemented
        return self._amount == other._amount

    def __lt__(self, other: "MicroDollar") -> bool:
        if not isinstance(other, MicroDollar):
            return NotImplemented
        return self._amount < other._amount

    def __le__(self, other: "MicroDollar") -> bool:
        if not isinstance(other, MicroDollar):
            return NotImplemented
        return self._amount <= other._amount

    def __gt__(self, other: "MicroDollar") -> bool:
        if not isinstance(other, MicroDollar):
            return NotImplemented
        return self._amount > other._amount

    def __ge__(self, other: "MicroDollar") -> bool:
        if not isinstance(other, MicroDollar):
            return NotImplemented
        return self._amount >= other._amount

    def __hash__(self) -> int:
        return hash(self._amount)

    def __bool__(self) -> bool:
        """Return True if amount is non-zero."""
        return self._amount != 0

    # =============================================
    # Display / Formatting
    # =============================================

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return f"<MicroDollar: {self._amount} (${self._amount / self.SCALE:.6f})>"

    def __str__(self) -> str:
        """User-friendly string."""
        return f"${self._amount / self.SCALE:.6f}"

    def to_ui_string(self) -> int:
        """
        Convert micro-credits to display credits for frontend.
        
        1 display credit = 1,000,000 micro-credits = $1.00
        
        Returns:
            Integer display credits (rounded down)
        """
        return self._amount // self.SCALE

    def to_dollars(self) -> float:
        """
        Convert to float dollars (for display only, not calculations).
        
        Returns:
            Float dollar amount
        """
        return self._amount / self.SCALE

    def to_dollars_string(self) -> str:
        """
        Format as dollar string for display.
        
        Returns:
            String like "$0.001500"
        """
        return f"${self._amount / self.SCALE:.6f}"
