import sys
import traceback

print(sys.executable)

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    print("matplotlib OK")
except Exception as e:
    print("matplotlib error")
    traceback.print_exc()

try:
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.svm import SVR
    from sklearn.model_selection import GridSearchCV, KFold, train_test_split
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.decomposition import PCA
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.impute import SimpleImputer
    print("sklearn OK")
except Exception as e:
    print("sklearn error")
    traceback.print_exc()

try:
    from scipy.fft import fft, fftfreq
    from scipy.signal import find_peaks
    print("scipy OK")
except Exception as e:
    print("scipy error")
    traceback.print_exc()
