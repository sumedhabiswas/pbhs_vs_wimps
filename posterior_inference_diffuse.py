import numpy as np
from scipy.integrate import trapz
from constants import e_egb, err_high_egb, fs_0
from diffuse_constraints import phi_ex
from posterior_inference_shared import f_min, f_max, Posterior


class DiffusePosterior(Posterior):
    """
    Class for performing posterior analysis with diffuse constraints. See the
    submission scripts and posterior_analysis_tutorial.ipynb for examples.
    """

    def __init__(self, m_pbh, n_pbh, merger_rate_prior="LF", sv_prior="U",
                 fs=fs_0, test=True):
        """Initializer.

        Parameters
        ----------
        m_pbh : float
            PBH mass.
        n_pbh : float
            Number of PBH detections
        merger_rate_prior : str
            Prior on R: either "LF" (log-flat, the conservative choice) or "J"
            (Jeffrey's).
        sv_prior: str
            Determines which prior to use for <sigma v>: "U" (uniform, the
            conservative choice) or "LF" (log-flat).
        fs : str
            DM annihilation final state.
        test : bool
            Setting this to True reads and writes all data tables to test/
            subdirectories. This is useful when worried about overwriting large
            tables that took a long time to compute.
        """
        super().__init__(m_pbh, n_pbh, merger_rate_prior, sv_prior, fs, test)

    def integrand(self, f, sv, m_dm):
        """Computes the value of the posterior integrand (appendix A2 of our
        paper).

        Parameters
        ----------
        f : float
            Relative PBH abundance.
        sv : float
            Self-annihilation cross section.
        m_dm : float
            DM mass.

        Returns
        -------
        float
            Integrand value.
        """
        def helper(f, sv, m_dm):
            log_prob = np.log(self.p_sv(sv) * self.p_f(f))
            phi_dms = phi_ex(e_egb, m_dm, sv, self.m_pbh, f, self.fs)
            log_prob += -0.5 * np.sum((phi_dms / err_high_egb)**2 +
                                      np.log(2 * np.pi * err_high_egb**2))

            return np.exp(log_prob)

        return np.vectorize(helper)(f, sv, m_dm)

    def _get_trapz_f_samples(self, fs, integrand_vals, frac=1e-10, n_low=75,
                             n_high=350):
        """Resamples log-spaced points below and above the posterior
        integrand's peak.

        Notes
        -----
        I found this is a good way to get accuracy with trapz that's at least
        as good as with quad, and much faster.

        Parameters
        ----------
        fs : np.array
            Array of f values with shape [N].
        integrand_vals : np.array
            Array of integrand values with shape [N, M]. The rows correspond to
            the values in fs and columns to different values of <sigma v>.
        n_low : int
            Number of points to sample below peak.
        n_high : int
            Number of points to sample above peak.

        Returns
        -------
        np.array
            Array of shape [n_low + n_peak + n_high, M] containing resampled f
            values.
        """
        # Define the integrand's peak
        integrand_max = integrand_vals.max(axis=0)
        min_sample_val = frac * integrand_max
        d = (np.sign(min_sample_val - integrand_vals[:-1]) -
             np.sign(min_sample_val - integrand_vals[1:]))

        # Select above and below peak
        f_peak = fs[integrand_vals.argmax(axis=0)]
        f_low = fs[np.argmax(d > 0, axis=0)]
        idx_high = np.argmax(d < 0, axis=0)
        idx_high[idx_high == 0] = -1
        f_high = fs[idx_high]

        return np.concatenate([np.geomspace(f_low, f_peak, n_low),
                               np.geomspace(f_peak, f_high, n_high)])

    def _get_posterior_val(self, sv, m_dm):
        """Computes the posterior for <sigma v>. Supports broadcasting over sv
        and m_dm.
        """
        def helper(sv, m_dm):
            # Compute integrand values over an initial f grid
            fs = np.geomspace(f_min, f_max, 20)
            sv_mg, f_mg = np.meshgrid(sv, fs)
            integrand_vals = self.integrand(f_mg, sv_mg, m_dm)

            # Resample fs
            f_mg = self._get_trapz_f_samples(
                fs, integrand_vals, n_low=50, n_high=150)
            sv_mg = sv * np.ones_like(f_mg)

            # Compute integral over new grid
            integrand_vals = self.integrand(f_mg, sv_mg, m_dm)
            integral_vals = trapz(integrand_vals, f_mg, axis=0)

            return integral_vals

        return np.vectorize(helper)(sv, m_dm)

    def filename_suffix(self):
        """Add extra info to filename"""
        return "diff_{}_prior".format(super().filename_suffix())
