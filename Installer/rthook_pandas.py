# Runtime hook: force pandas C-extension initialisation order
#
# When PyInstaller freezes an app, pandas' Cython extensions can be loaded
# in the wrong order, causing:
#   AttributeError: partially initialized module 'pandas' has no attribute
#   '_pandas_datetime_CAPI' (most likely due to a circular import)
#
# The fix is to import the tslibs datetime C-extension explicitly FIRST,
# before anything else touches pandas.  PyInstaller runtime hooks run before
# the frozen application's own imports, so this resolves the ordering issue.

import pandas._libs.tslibs.base          # noqa: F401
import pandas._libs.tslibs.np_datetime   # noqa: F401
import pandas._libs.tslibs.nattype       # noqa: F401
import pandas._libs.tslibs.timestamps    # noqa: F401
import pandas._libs.tslibs.timedeltas    # noqa: F401
import pandas._libs.tslibs.period        # noqa: F401
import pandas._libs.tslibs.offsets       # noqa: F401
import pandas._libs.tslibs.parsing       # noqa: F401
