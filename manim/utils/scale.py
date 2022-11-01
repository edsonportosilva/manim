import math
from typing import TYPE_CHECKING, Any, Dict, Iterable, List

__all__ = ["LogBase", "LinearBase"]

from ..mobject.numbers import Integer

if TYPE_CHECKING:
    from manim.mobject.mobject import Mobject


class _ScaleBase:
    """Scale baseclass for graphing/functions."""

    def __init__(self, custom_labels: bool = False):
        """
        Parameters
        ----------
        custom_labels
            Whether to create custom labels when plotted on a :class:`~.NumberLine`.
        """
        self.custom_labels = custom_labels

    def function(self, value: float) -> float:
        """The function that will be used to scale the values.

        Parameters
        ----------
        value
            The number/``np.ndarray`` to be scaled.

        Returns
        -------
        float
            The value after it has undergone the scaling.

        Raises
        ------
        NotImplementedError
            Must be subclassed.
        """
        raise NotImplementedError

    def inverse_function(self, value: float) -> float:
        """The inverse of ``function``. Used for plotting on a particular axis.

        Raises
        ------
        NotImplementedError
            Must be subclassed.
        """
        raise NotImplementedError

    def get_custom_labels(
        self,
        val_range: Iterable[float],
    ) -> Iterable["Mobject"]:
        """Custom instructions for generating labels along an axis.

        Parameters
        ----------
        val_range
            The position of labels. Also used for defining the content of the labels.

        Returns
        -------
        Dict
            A list consisting of the labels.
            Can be passed to :meth:`~.NumberLine.add_labels() along with ``val_range``.

        Raises
        ------
        NotImplementedError
            Can be subclassed, optional.
        """
        raise NotImplementedError


class LinearBase(_ScaleBase):
    def __init__(self, scale_factor: float = 1.0):
        """The default scaling class.

        Parameters
        ----------
        scale_factor
            The slope of the linear function, by default 1.0
        """

        super().__init__()
        self.scale_factor = scale_factor

    def function(self, value: float) -> float:
        """Multiplies the value by the scale factor.

        Parameters
        ----------
        value
            Value to be multiplied by the scale factor.
        """
        return self.scale_factor * value

    def inverse_function(self, value: float) -> float:
        """Inverse of function. Divides the value by the scale factor.

        Parameters
        ----------
        value
            value to be divided by the scale factor.
        """
        return value / self.scale_factor


class LogBase(_ScaleBase):
    def __init__(self, base: float = 10, custom_labels: bool = True):
        """Scale for logarithmic graphs/functions.

        Parameters
        ----------
        base
            The base of the log, by default 10.
        custom_labels : bool, optional
            For use with :class:`~.Axes`:
            Whetherer or not to include ``LaTeX`` axis labels, by default True.

        Examples
        --------

        .. code-block:: python

            func = ParametricFunction(lambda x: x, scaling=LogBase(base=2))

        """
        super().__init__()
        self.base = base
        self.custom_labels = custom_labels

    def function(self, value: float) -> float:
        """Scales the value to fit it to a logarithmic scale.``self.function(5)==10**5``"""
        return self.base ** value

    def inverse_function(self, value: float) -> float:
        """Inverse of ``function``. The value must be greater than 0"""
        if value <= 0:
            raise ValueError(
                "log(0) is undefined. Make sure the value is in the domain of the function"
            )
        return math.log(value, self.base)

    def get_custom_labels(
        self,
        val_range: Iterable[float],
        unit_decimal_places: int = 0,
        **base_config: Dict[str, Any],
    ) -> List["Mobject"]:
        """Produces custom :class:`~.Integer` labels in the form of ``10^2``.

        Parameters
        ----------

        val_range
            The iterable of values used to create the labels. Determines the exponent.
        units_decimal_places
            The number of decimal places to include in the exponent
        base_config
            Additional arguments to be passed to :class:`~.Integer`.
        """

        return [
            Integer(
                self.base,
                unit="^{%s}"
                % (f"{self.inverse_function(i):.{unit_decimal_places}f}"),
                **base_config,
            )
            for i in val_range
        ]
