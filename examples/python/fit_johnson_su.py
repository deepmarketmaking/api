import numpy as np
from scipy.stats import johnsonsu
from scipy.optimize import minimize
from scipy.stats import gaussian_kde
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def fit_johnson_su(percentiles, percentile_values):
    # Convert percentiles from percentages to probability values
    p_values = np.array(percentiles) / 100.0
    y_values = np.array(percentile_values)

    # Define the error function that we want to minimize
    def error_function(params):
        gamma, delta, loc, scale = params
        # Calculate the theoretical percentiles using the Johnson S.U. distribution with the given parameters
        theoretical_values = johnsonsu.ppf(p_values, gamma, delta, loc=loc, scale=scale)
        # Calculate the sum of squared errors between the actual and theoretical values
        error = np.sum((y_values - theoretical_values) ** 2)
        return error

    # Initial guess for the parameters
    gamma_initial = 0.001
    delta_initial = 2.0
    loc_initial = np.mean(y_values)
    scale_initial = np.std(y_values)

    # Use minimize to find the optimal parameters
    result = minimize(
        error_function,
        [gamma_initial, delta_initial, loc_initial, scale_initial],
        method='Nelder-Mead'
    )

    # Constraints: Keep parameters within reasonable ranges
    #bounds = [(-10, 10), (1e-10, 10), (percentiles[0], percentiles[-1]), (scale_initial * 0.01, scale_initial * 10)]

    result = minimize(
        error_function,
        [gamma_initial, delta_initial, loc_initial, scale_initial],
        method='L-BFGS-B',
        #bounds=bounds
    )

    # Extract the optimal parameters
    gamma_optimal, delta_optimal, loc_optimal, scale_optimal = result.x

    # Calculate the error metric for the best fit
    best_fit_error = error_function([gamma_optimal, delta_optimal, loc_optimal, scale_optimal])

    return gamma_optimal, delta_optimal, loc_optimal, scale_optimal, best_fit_error


def plot_cdf_of_fitted_johnson_su_distribution(plot_filename, percentiles, percentile_values, gamma, delta, loc, scale):
    # Calculate the CDF of the original data
    p_values = np.array(percentiles) / 100.0

    # Generate the CDF using the fitted Johnson S.U. distribution
    x_values = np.linspace(min(percentile_values) - 1, max(percentile_values) + 1, 1000)
    cdf_fitted = johnsonsu.cdf(x_values, gamma, delta, loc=loc, scale=scale)

    # Plotting the results
    plt.figure(figsize=(10, 6))
    plt.plot(x_values, cdf_fitted, label='Fitted Johnson S.U. CDF', color='blue')
    plt.scatter(percentile_values, p_values, color='red', label='Original Percentiles')
    plt.xlabel('Value')
    plt.ylabel('Cumulative Probability')
    plt.title('Comparison of Fitted Johnson S.U. CDF and Original Percentiles')
    plt.legend()
    plt.grid(True)

    # Save the figure to a file
    plt.savefig(plot_filename, dpi=300)

    # Optionally, close the plot to free up memory
    plt.close()


def plot_pdf_of_fitted_johnson_su_distribution(plot_filename, percentiles, percentile_values, gamma, delta, loc, scale):
    x_values = np.linspace(min(percentile_values) - 1, max(percentile_values) + 1, 1000)

    # Plot the PDF comparison

    # Calculate the PDF from the fitted Johnson S.U. distribution
    pdf_fitted = johnsonsu.pdf(x_values, gamma, delta, loc=loc, scale=scale)

    # Estimate the empirical PDF from the provided percentiles using a kernel density estimate (KDE)
    # Corrected weights: The weights should be based on differences between percentiles
    weights = np.diff([0] + percentiles + [100]) / 100.0
    # Adjust weights to correspond with each percentile value
    weights = (weights[:-1] + weights[1:]) / 2

    kde = gaussian_kde(percentile_values, weights=weights, bw_method='scott')
    pdf_empirical = kde(x_values)

    # Plotting the results
    plt.figure(figsize=(10, 6))
    plt.plot(x_values, pdf_fitted, label='Fitted Johnson S.U. PDF', color='blue')
    plt.plot(x_values, pdf_empirical, label='Empirical PDF from Percentiles', color='red', linestyle='--')
    plt.xlabel('Value')
    plt.ylabel('Density')
    plt.title('Comparison of Fitted Johnson S.U. PDF and Empirical PDF')
    plt.legend()
    plt.grid(True)

    # Save the figure to a file
    plt.savefig(plot_filename, dpi=300)


if __name__ == '__main__':
    # Example usage
    percentiles = [5, 25, 50, 75, 95]
    percentile_values = [1.65, 2.35, 3.00, 3.65, 4.35]

    gamma, delta, loc, scale, error = fit_johnson_su(percentiles, percentile_values)
    print(f"Gamma: {gamma}")
    print(f"Delta: {delta}")
    print(f"Location (loc): {loc}")
    print(f"Scale: {scale}")
    print(f"Error Metric (Sum of Squared Errors): {error}")

    plot_cdf_of_fitted_johnson_su_distribution('fitted_johnson_su_cdf.png',
                                               percentiles, percentile_values,
                                               gamma, delta, loc, scale)

    plot_pdf_of_fitted_johnson_su_distribution('fitted_johnson_su_pdf.png',
                                               percentiles, percentile_values,
                                               gamma, delta, loc, scale)
