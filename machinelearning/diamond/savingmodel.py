import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pickle

def main():
    with open("diamond_model_complete.pkl", "rb") as f:
        saved_data = pickle.load(f)

    model = saved_data["model"]

    X_test_scaled = pd.read_csv("testdatascaled.csv")
    print(model.predict(X_test_scaled))

if __name__ == "__main__":
    main()