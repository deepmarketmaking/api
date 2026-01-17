import numpy as np
from scipy.stats import norm
from scipy.optimize import minimize


def fit_normal_distribution(percentiles, percentile_values):
    # Convert percentiles from percentages to probability values
    p_values = np.array(percentiles) / 100.0
    y_values = np.array(percentile_values)

    # Define the error function that we want to minimize
    def error_function(params):
        mu, sigma = params
        # Calculate the theoretical percentiles using the normal distribution with given mu and sigma
        theoretical_values = norm.ppf(p_values, loc=mu, scale=sigma)
        # Calculate the sum of squared errors between the actual and theoretical values
        error = np.sum((y_values - theoretical_values) ** 2)
        return error

    # Initial guess for mu and sigma based on the data
    mu_initial = np.mean(y_values)
    sigma_initial = np.std(y_values)

    # Use minimize to find the optimal mu and sigma
    result = minimize(error_function, [mu_initial, sigma_initial], method='Nelder-Mead')

    # Extract the optimal parameters
    mu_optimal, sigma_optimal = result.x

    # Calculate the error metric for the best fit
    best_fit_error = error_function([mu_optimal, sigma_optimal])

    return mu_optimal, sigma_optimal, best_fit_error


if __name__ == '__main__':
    # Example usage
    percentiles = [5, 25, 50, 75, 95]
    percentile_values = [1.65, 2.35, 3.00, 3.65, 4.35]

    mu, sigma, error = fit_normal_distribution(percentiles, percentile_values)
    print(f"Mean (mu): {mu}")
    print(f"Standard Deviation (sigma): {sigma}")
    print(f"Error Metric (Sum of Squared Errors): {error}")