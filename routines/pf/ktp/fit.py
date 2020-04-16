"""
  Fit the rate constants read from the MESS output to
  Arrhenius, Plog, or Troe expressions
"""

import os
import numpy
import ratefit
import chemkin_io

# New libs
from routines.pf.ktp import rates as messrates
# from lib.outpt import chemkin as cout
from lib.phydat import phycon


def fit_rates(inp_temps, inp_pressures, inp_tunit, inp_punit,
              pes_formula_str, idx_dct,
              mess_path, fit_method, pdep_fit,
              arrfit_thresh):
    """ Parse the MESS output and fit the rates to
        Arrhenius expressions written as CHEMKIN strings
    """

    # pf_levels.append(ene_str)
    # chemkin_header_str = cout.run_ckin_header(pf_levels, pf_model)
    # chemkin_header_str += cout.get_ckin_ene_lvl_str(pf_levels, ene_coeff)
    # chemkin_header_str += '\n'
    chemkin_header_str = 'HEADER\n'
    chemkin_poly_str = chemkin_header_str
    chemkin_str = ''
    starting_path = os.getcwd()
    ckin_path = ''.join([starting_path, '/ckin'])
    if not os.path.exists(ckin_path):
        os.mkdir(ckin_path)
    labels = idx_dct.values()
    names = idx_dct.keys()
    for lab_i, name_i in zip(labels, names):
        a_conv_factor = phycon.NAVO if 'W' not in lab_i else 1.00
        if 'F' not in lab_i and 'B' not in lab_i:
            for lab_j, name_j in zip(labels, names):
                if 'F' not in lab_j and 'B' not in lab_j and lab_i != lab_j:

                    # Set name
                    reaction = name_i + '=' + name_j

                    # Read the rate constants out of the mess outputs
                    ktp_dct = messrates.read_rates(
                        inp_temps, inp_pressures, inp_tunit, inp_punit,
                        lab_i, lab_j, mess_path, pdep_fit,
                        bimol=numpy.isclose(a_conv_factor, 6.0221e23))

                    # Get the desired fits in the form of CHEMKIN strs
                    if fit_method == 'arrhenius':
                        chemkin_str += perform_arrhenius_fits(
                            ktp_dct, reaction, mess_path,
                            a_conv_factor, arrfit_thresh)
                    elif fit_method == 'troe':
                        pass
                        # chemkin_str += perform_troe_fits(
                        #     ktp_dct, reaction, mess_path,
                        #     troe_param_fit_lst,
                        #     a_conv_factor, err_thresh)

                    # Write the CHEMKIN strings
                    chemkin_poly_str += '\n'
                    chemkin_poly_str += chemkin_str
                    chemkin_str = chemkin_header_str + chemkin_str
                    print(chemkin_str)

                    # Print the results for each channel to a file
                    pes_chn_lab = pes_formula_str + '_' + name_i + '_' + name_j
                    ckin_name = os.path.join(ckin_path, pes_chn_lab+'.ckin')
                    with open(ckin_name, 'w') as cfile:
                        cfile.write(chemkin_str)

    # Print the results for the whole PES to a file
    with open(os.path.join(ckin_path, pes_formula_str+'.ckin'), 'a') as cfile:
        cfile.write(chemkin_poly_str)


def perform_arrhenius_fits(ktp_dct, reaction, mess_path,
                           a_conv_factor, err_thresh):
    """ Read the rates for each channel and perform the fits
    """
    # Fit rate constants to single Arrhenius expressions
    sing_params_dct, sing_fit_temp_dct, sing_fit_success = mod_arr_fit(
        ktp_dct, mess_path, fit_type='single', fit_method='python',
        t_ref=1.0, a_conv_factor=a_conv_factor)
    if sing_fit_success:
        print('\nSuccessful fit to Single Arrhenius at all T, P')

    # Assess the errors of the single Arrhenius Fit
    sing_fit_err_dct = assess_arr_fit_err(
        sing_params_dct, ktp_dct,
        fit_type='single',
        t_ref=1.0, a_conv_factor=a_conv_factor)
    print('\nFitting Parameters and Errors from Single Arrhenius Fit')
    for pressure, params in sing_params_dct.items():
        print(pressure, params)
    for pressure, errs in sing_fit_err_dct.items():
        print(pressure, errs)

    # Assess single fitting errors:
    # are they within threshold at each pressure
    sgl_fit_good = max((
        vals[1] for vals in sing_fit_err_dct.values())) < err_thresh

    # Assess if a double Arrhenius fit is possible
    dbl_fit_poss = all(
        len(ktp_dct[p][0]) >= 6 for p in ktp_dct)

    # Write chemkin string for single/double fit, based on errors
    chemkin_str = ''
    if sgl_fit_good:
        print('\nSingle fit errors acceptable: Using single fits')
        chemkin_str += chemkin_io.writer.reaction.plog(
            reaction, sing_params_dct,
            err_dct=sing_fit_err_dct, temp_dct=sing_fit_temp_dct)
    elif not sgl_fit_good and dbl_fit_poss:
        print('\nSingle fit errs too large & double fit possible:',
              ' Trying double fit')

        # Fit rate constants to double Arrhenius expressions
        doub_params_dct, doub_fit_temp_dct, doub_fit_suc = mod_arr_fit(
            ktp_dct, mess_path, fit_type='double',
            fit_method='dsarrfit', t_ref=1.0,
            a_conv_factor=a_conv_factor)

        if doub_fit_suc:
            print('\nSuccessful fit to Double Arrhenius at all T, P')
            # Assess the errors of the single Arrhenius Fit
            doub_fit_err_dct = assess_arr_fit_err(
                doub_params_dct, ktp_dct, fit_type='double',
                t_ref=1.0, a_conv_factor=a_conv_factor)
            chemkin_str += chemkin_io.writer.reaction.plog(
                reaction, doub_params_dct,
                err_dct=doub_fit_err_dct, temp_dct=doub_fit_temp_dct)
        else:
            print('\nDouble Arrhenius Fit failed for some reason:',
                  ' Using Single fits')
            chemkin_str += chemkin_io.writer.reaction.plog(
                reaction, sing_params_dct,
                err_dct=sing_fit_err_dct, temp_dct=sing_fit_temp_dct)
    elif not sgl_fit_good and not dbl_fit_poss:
        print('\nNot enough temperatures for a double fit:',
              ' Using single fits')
        chemkin_str += chemkin_io.writer.reaction.plog(
            reaction, sing_params_dct,
            err_dct=sing_fit_err_dct, temp_dct=sing_fit_temp_dct)

    return chemkin_str


def mod_arr_fit(ktp_dct, mess_path, fit_type='single', fit_method='dsarrfit',
                t_ref=1.0, a_conv_factor=1.0):
    """
    Routine for a single reaction:
        (1) Grab high-pressure and pressure-dependent rate constants
            from a MESS output file
        (2) Fit rate constants to an Arrhenius expression
    """

    assert fit_type in ('single', 'double')

    # Dictionaries to store info; indexed by pressure (given in fit_ps)
    fit_param_dct = {}
    fit_temp_dct = {}

    # Calculate the fitting parameters from the filtered T,k lists
    for pressure, tk_arr in ktp_dct.items():

        # Set the temperatures and rate constants
        temps = tk_arr[0]
        rate_constants = tk_arr[1]

        # Fit rate constants using desired Arrhenius fit
        if fit_type == 'single':
            fit_params = ratefit.fit.arrhenius.single(
                temps, rate_constants, t_ref, fit_method,
                dsarrfit_path=mess_path, a_conv_factor=a_conv_factor)
        elif fit_type == 'double':
            fit_params = ratefit.fit.arrhenius.double(
                temps, rate_constants, t_ref, fit_method,
                dsarrfit_path=mess_path, a_conv_factor=a_conv_factor)

        # Store the fitting parameters in a dictionary
        fit_param_dct[pressure] = fit_params

        # Store the temperatures used to fit in a dictionary
        fit_temp_dct[pressure] = [min(temps), max(temps)]

    # Check if the desired fits were successful at each pressure
    fit_success = all(params for params in fit_param_dct.values())

    return fit_param_dct, fit_temp_dct, fit_success


def assess_arr_fit_err(fit_param_dct, ktp_dct, fit_type='single',
                       t_ref=1.0, a_conv_factor=1.0):
    """ Determine the errors in the rate constants that arise
        from the Arrhenius fitting procedure
    """

    fit_k_dct = {}
    fit_err_dct = {}

    assert fit_type in ('single', 'double')

    # Calculate fitted rate constants using the fitted parameters
    for pressure, params in fit_param_dct.items():

        # Set the temperatures
        temps = ktp_dct[pressure][0]

        # Calculate fitted rate constants, based on fit type
        if fit_type == 'single':
            fit_ks = ratefit.calc.single_arrhenius(
                params[0], params[1], params[2],
                t_ref, temps)
        elif fit_type == 'double':
            fit_ks = ratefit.calc.double_arrhenius(
                params[0], params[1], params[2],
                params[3], params[4], params[5],
                t_ref, temps)

        # Store the fitting parameters in a dictionary
        fit_k_dct[pressure] = fit_ks / a_conv_factor

    # Calculute the error between the calc and fit ks
    for pressure, fit_ks in fit_k_dct.items():

        calc_ks = ktp_dct[pressure][1]
        mean_avg_err, max_avg_err = ratefit.calc.fitting_errors(
            calc_ks, fit_ks)

        # Store in a dictionary
        fit_err_dct[pressure] = [mean_avg_err, max_avg_err]

    return fit_err_dct


def perform_troe_fits(ktp_dct, reaction, mess_path,
                      troe_param_fit_lst, a_conv_factor, err_thresh):
    """ Fit rate constants to Troe parameters
    """

    # Dictionaries to store info; indexed by pressure (given in fit_ps)
    fit_param_dct = {}
    fit_temp_dct = {}

    # Calculate the fitting parameters from the filtered T,k lists
    new_dct = {}
    for key, val in ktp_dct.items():
        if key != 'high':
            new_dct[key] = val
    inv_ktp_dct = ratefit.fit.flip_ktp_dct(new_dct)
    fit_params = ratefit.fit.troe.std_form(
        inv_ktp_dct, troe_param_fit_lst, mess_path,
        highp_a=8.1e-11, highp_n=-0.01, highp_ea=1000.0,
        lowp_a=8.1e-11, lowp_n=-0.01, lowp_ea=1000.0,
        alpha=0.19, ts1=590, ts2=1.e6, ts3=6.e4,
        fit_tol1=1.0e-8, fit_tol2=1.0e-8,
        a_conv_factor=1.0)

    # Store the parameters in the fit dct
    for pressure, tk_arr in ktp_dct.items():

        # Store the fitting parameters in a dictionary
        fit_param_dct[pressure] = fit_params

        # Store the temperatures used to fit in a dictionary
        temps = tk_arr[0]
        fit_temp_dct[pressure] = [min(temps), max(temps)]

    # Check if the desired fits were successful at each pressure
    fit_success = all(params for params in fit_param_dct.values())

    # Calculate the errors from the Troe fits
    if fit_success:
        fit_err_dct = assess_troe_fit_err(
            fit_param_dct, ktp_dct, t_ref=1.0, a_conv_factor=a_conv_factor)
        fit_good = max((vals[1] for vals in fit_err_dct.values())) < err_thresh
        if fit_good:
            chemkin_str = chemkin_io.writer.reaction.troe(
                reaction,
                [fit_params[0], fit_params[1], fit_params[2]],
                [fit_params[3], fit_params[4], fit_params[5]],
                [fit_params[6], fit_params[8], fit_params[7], fit_params[9]],
                colliders=())

        # Store the fitting parameters in a dictionary
    else:
        chemkin_str = ''

    return chemkin_str


def assess_troe_fit_err(fit_param_dct, ktp_dct, t_ref=1.0, a_conv_factor=1.0):
    """ Determine the errors in the rate constants that arise
        from the Arrhenius fitting procedure
    """

    fit_k_dct = {}
    fit_err_dct = {}

    # Calculate fitted rate constants using the fitted parameters
    fit_pressures = fit_param_dct.keys()
    for pressure, params in fit_param_dct.items():

        # Set the temperatures
        temps = ktp_dct[pressure][0]

        # Calculate fitted rate constants, based on fit type
        highp_arrfit_ks = ratefit.calc.single_arrhenius(
            params[0], params[1], params[2],
            t_ref, temps)
        lowp_arrfit_ks = ratefit.calc.single_arrhenius(
            params[3], params[4], params[5],
            t_ref, temps)
        fit_ks = ratefit.calc.troe(
            highp_arrfit_ks, lowp_arrfit_ks, fit_pressures, temps,
            params[6], params[8], params[7], ts2=params[9])

        # Store the fitting parameters in a dictionary
        fit_k_dct[pressure] = fit_ks / a_conv_factor

    # Calculute the error between the calc and fit ks
    for pressure, fit_ks in fit_k_dct.items():

        calc_ks = ktp_dct[pressure][1]
        mean_avg_err, max_avg_err = ratefit.calc.fitting_errors(
            calc_ks, fit_ks)

        # Store in a dictionary
        fit_err_dct[pressure] = [mean_avg_err, max_avg_err]

    return fit_err_dct
