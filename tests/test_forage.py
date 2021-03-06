"""InVEST forage model tests."""

import unittest
import tempfile
import shutil
import os
import math

import numpy
import pandas
from osgeo import osr
from osgeo import gdal

import pygeoprocessing

SAMPLE_DATA = "C:/Users/ginge/Dropbox/sample_inputs"
REGRESSION_DATA = "C:/Users/ginge/Documents/NatCap/regression_test_data"
PROCESSING_DIR = None
TEST_AOI = "C:/Users/ginge/Dropbox/sample_inputs/test_aoi.shp"

_TARGET_NODATA = -1.0
_IC_NODATA = float(numpy.finfo('float32').min)
_SV_NODATA = -1.0

NROWS = 3
NCOLS = 3

numpy.random.seed(100)


def create_random_raster(
        target_path, lower_bound, upper_bound, nrows=NROWS, ncols=NCOLS):
    """Create a small raster of random floats.

    The raster will have nrows rows and ncols columns and will be in the
    unprojected coordinate system WGS 1984. The values in the raster
    will be between `lower_bound` (included) and `upper_bound`
    (excluded).

    Parameters:
        target_path (string): path to result raster
        lower_bound (float): lower limit of range of random values
            (included)
        upper_bound (float): upper limit of range of random values
            (excluded)

    Returns:
        None

    """
    geotransform = [0, 0.0001, 0, 44.5, 0, 0.0001]
    n_bands = 1
    datatype = gdal.GDT_Float32
    projection = osr.SpatialReference()
    projection.SetWellKnownGeogCS('WGS84')
    driver = gdal.GetDriverByName('GTiff')
    target_raster = driver.Create(
        target_path.encode('utf-8'), ncols, nrows, n_bands,
        datatype)
    target_raster.SetProjection(projection.ExportToWkt())
    target_raster.SetGeoTransform(geotransform)
    target_band = target_raster.GetRasterBand(1)
    target_band.SetNoDataValue(_TARGET_NODATA)

    random_array = numpy.random.uniform(
        lower_bound, upper_bound, (nrows, ncols))
    target_band.WriteArray(random_array)
    target_raster = None


def create_complementary_raster(
        raster1_path, raster2_path, result_raster_path):
    """Create a raster to sum inputs to 1.

    The sum of the two input rasters and the result raster will be
    1.

    Parameters:
        raster1_path (string): path to raster of floast between 0 and 1
        raster2_path (string): path to raster of floast between 0 and 1
        result_raster_path (string): path to result raster

    Side effects:
        modifies or creates the raster indicated by `result_raster_path`

    Returns:
        None

    """
    def complement_op(input1, input2):
        """Generate an array that adds to 1 with input1 and input2."""
        result_raster = numpy.empty(input1.shape, dtype=numpy.float32)
        result_raster[:] = _TARGET_NODATA
        valid_mask = (
            (input1 != _TARGET_NODATA)
            & (input2 != _TARGET_NODATA))

        result_raster[valid_mask] = (
            1. - (input1[valid_mask] + input2[valid_mask]))
        return result_raster

    pygeoprocessing.raster_calculator(
        [(path, 1) for path in [raster1_path, raster2_path]],
        complement_op, result_raster_path, gdal.GDT_Float32,
        _TARGET_NODATA)


def insert_nodata_values_into_raster(target_raster, nodata_value):
    """Insert nodata at arbitrary locations in `target_raster`."""
    def insert_op(prior_copy):
        modified_copy = prior_copy
        if (prior_copy.shape[0] * prior_copy.shape[1]) == 1:
            n_vals = 1
        else:
            n_vals = numpy.random.randint(
                1, (prior_copy.shape[0] * prior_copy.shape[1]))
        insertions = 0
        while insertions < n_vals:
            row = numpy.random.randint(0, prior_copy.shape[0])
            col = numpy.random.randint(0, prior_copy.shape[1])
            modified_copy[row, col] = nodata_value
            insertions += 1
        return modified_copy

    prior_copy = os.path.join(
        os.path.dirname(target_raster), 'prior_to_insert_nodata.tif')
    shutil.copyfile(target_raster, prior_copy)

    pygeoprocessing.raster_calculator(
        [(prior_copy, 1)],
        insert_op, target_raster,
        gdal.GDT_Float32, nodata_value)

    os.remove(prior_copy)


def create_constant_raster(target_path, fill_value, n_cols=1, n_rows=1):
    """Create a single-pixel raster with value `fill_value`."""
    geotransform = [0, 1, 0, 44.5, 0, 1]
    n_bands = 1
    datatype = gdal.GDT_Float32
    projection = osr.SpatialReference()
    projection.SetWellKnownGeogCS('WGS84')
    driver = gdal.GetDriverByName('GTiff')
    target_raster = driver.Create(
        target_path.encode('utf-8'), n_cols, n_rows, n_bands,
        datatype)
    target_raster.SetProjection(projection.ExportToWkt())
    target_raster.SetGeoTransform(geotransform)
    target_band = target_raster.GetRasterBand(1)
    target_band.SetNoDataValue(_TARGET_NODATA)
    target_band.Fill(fill_value)
    target_raster = None


def insert_nodata_values_into_array(target_array, nodata_value):
    """Insert nodata at arbitrary locations in `target_array`."""
    modified_array = target_array
    n_vals = numpy.random.randint(
        0, (target_array.shape[0] * target_array.shape[1]))
    insertions = 0
    while insertions < n_vals:
        row = numpy.random.randint(0, target_array.shape[0])
        col = numpy.random.randint(0, target_array.shape[1])
        modified_array[row, col] = nodata_value
        insertions += 1
    return modified_array


def calc_raster_difference_stats(
        raster1_path, raster2_path, aggregate_vector_path):
    """Calculate summary of the difference between two rasters.

    Calculate the pixel-based difference between the raster indicated by
    `raster1_path` and the raster indicated by `raster2_path`. Calculate
    summary statistics from the difference raster falling inside a vector-
    based area of interest.

    Parameters:
        raster1_path (string): path to raster to take the difference from
        raster2_path (string): path to raster to subtract from raster1
        aggregate_vector_path (string): area over which to calculate zonal
            statistics on the difference between the two rasters

    Returns:
        nested dictionary indexed by aggregating feature id, and then by one
        of 'min' 'max' 'sum' 'count' and 'nodata_count'.  Example:
        {0: {'min': 0, 'max': 1, 'sum': 1.7, count': 3, 'nodata_count': 1}}

    """
    def raster_difference_op(raster1, raster2):
        """Subtract raster2 from raster1 without removing nodata values."""
        valid_mask = (
            (~numpy.isclose(raster1, raster1_nodata)) &
            (~numpy.isclose(raster2, raster2_nodata)))
        result = numpy.empty(raster1.shape, dtype=numpy.float32)
        result[:] = _TARGET_NODATA
        result[valid_mask] = raster1[valid_mask] - raster2[valid_mask]
        return result

    raster1_nodata = pygeoprocessing.get_raster_info(raster1_path)['nodata'][0]
    raster2_nodata = pygeoprocessing.get_raster_info(raster2_path)['nodata'][0]

    with tempfile.NamedTemporaryFile(prefix='raster_diff') as target_file:
        target_path = target_file.name

    pygeoprocessing.raster_calculator(
        [(path, 1) for path in [raster1_path, raster2_path]],
        raster_difference_op, target_path, gdal.GDT_Float32,
        _TARGET_NODATA)

    zonal_stats = pygeoprocessing.zonal_statistics(
        (target_path, 1), aggregate_vector_path)
    return zonal_stats


def monthly_N_fixation_point(
        precip, annual_precip, baseNdep, epnfs_2, prev_minerl_1_1):
    """Add monthly N fixation to surface mineral N pool.

    Monthly N fixation is calculated from annual N deposition according to
    the ratio of monthly precipitation to annual precipitation.

    Parameters:
        precip (float): input, monthly precipitation
        annual_precip (float): derived, annual precipitation
        baseNdep (float): derived, annual atmospheric N deposition
        epnfs_2 (float): parameter, intercept of regression
            predicting N deposition from annual precipitation
        prev_minerl_1_1 (float): state variable, mineral N in the
            surface layer in previous month

    Returns:
        minerl_1_1, updated mineral N in the surface layer

    """
    wdfxm = (
        baseNdep * (precip / annual_precip) + epnfs_2 *
        min(annual_precip, 100.) * (precip / annual_precip))
    minerl_1_1 = prev_minerl_1_1 + wdfxm
    return minerl_1_1


def rprpet_point(pet, snowmelt, avh2o_3, precip):
    """Calculate the ratio of precipitation to ref evapotranspiration.

    The ratio of precipitation or snowmelt to reference
    evapotranspiration influences agdefac and bgdefac, the above- and
    belowground decomposition factors.

    Parameters:
        pet (float): derived, reference evapotranspiration
        snowmelt (float): derived, snowmelt occuring this month
        avh2o_3 (float): derived, moisture in top two soil layers
        precip (float): input, precipitation for this month

    Returns:
        rprpet, the ratio of precipitation or snowmelt to reference
            evapotranspiration

    """
    if snowmelt > 0:
        rprpet = snowmelt / pet
    else:
        rprpet = (avh2o_3 + precip) / pet
    return rprpet


def defac_point(
        snow, min_temp, max_temp, rprpet, teff_1, teff_2, teff_3, teff_4):
    """Point-based version of `calc_defac`.

    The decomposition factor reflects the influence of soil temperature and
    moisture on decomposition. Lines 151-200, Cycle.f.

    Parameters:
        snow (float): standing snowpack
        min_temp (float): average minimum temperature for the month
        max_temp (float): average maximum temperature for the month
        rprpet (float): ratio of precipitation or snowmelt to
            reference evapotranspiration
        teff_1 (float): x location of inflection point for
            calculating the effect of soil temperature on decomposition
            factor
        teff_2 (float): y location of inflection point for
            calculating the effect of soil temperature on decomposition
            factor
        teff_3 (float): step size for calculating the effect
            of soil temperature on decomposition factor
        teff_4 (float): lope of the line at the inflection
            point, for calculating the effect of soil temperature on
            decomposition factor

    Returns:
        defac, aboveground and belowground decomposition factor

    """
    if rprpet > 9:
        agwfunc = 1
    else:
        agwfunc = 1. / (1 + 30 * math.exp(-8.5 * rprpet))
    if snow > 0:
        stemp = 0
    else:
        stemp = (min_temp + max_temp) / 2.
    tfunc = max(
        0.01, (teff_2 + (teff_3 / math.pi) * numpy.arctan(math.pi *
            teff_4 * (stemp - teff_1))) /
        (teff_2 + (teff_3 / math.pi) * numpy.arctan(math.pi *
            teff_4 * (30.0 - teff_1))))
    defac = max(0, tfunc * agwfunc)
    return defac


def calc_anerb_point(
        rprpet, pevap, drain, aneref_1, aneref_2, aneref_3):
    """Calculate effect of soil anaerobic conditions on decomposition.

    The impact of soil anaerobic conditions on decomposition is
    calculated from soil moisture and reference evapotranspiration.
    Anerob.f.

    Parameters:
        rprpet (float): ratio of precipitation or snowmelt to
            reference evapotranspiration
        pevap (float): reference evapotranspiration
        drain (float): the fraction of excess water lost by
            drainage. Indicates whether a soil is sensitive for
            anaerobiosis (drain = 0) or not (drain = 1)
        aneref_1 (float): value of rprpet below which there
            is no negative impact of soil anaerobic conditions on
            decomposition
        aneref_2 (float): value of rprpet above which there
            is maximum negative impact of soil anaerobic conditions on
            decomposition
        aneref_3 (float): minimum value of the impact of
            soil anaerobic conditions on decomposition

    Returns:
        anerb, the effect of soil anaerobic conditions on decomposition

    """
    anerb = 1
    if rprpet > aneref_1:
        xh2o = (rprpet - aneref_1) * pevap * (1. - drain)
        if xh2o > 0:
            newrat = aneref_1 + (xh2o / pevap)
            slope = (1. - aneref_3) / (aneref_1 - aneref_2)
            anerb = 1. + slope * (newrat - aneref_1)
        anerb = max(anerb, aneref_3)
    return anerb


def bgdrat_point(aminrl, varat_1_iel, varat_2_iel, varat_3_iel):
    """Calculate required C/iel ratio for belowground decomposition.

    When belowground material decomposes, its nutrient content is
    compared to this ratio to check whether nutrient content is
    sufficiently high to allow decomposition. This ratio is calculated at
    each decomposition time step.

    Parameters:
        aminrl (float): mineral <iel> (N or P) in top soil layer, averaged
            across decomposition time steps
        varat_1_iel (float): parameter, maximum C/iel ratio
        varat_2_iel (float): parameter, minimum C/iel ratio
        varat_3_iel (float): parameter, amount of iel present when minimum
            ratio applies

    Returns:
        bgdrat, the required C/iel ratio for decomposition

    """
    if aminrl <= 0:
        bgdrat = varat_1_iel
    elif aminrl > varat_3_iel:
        bgdrat = varat_2_iel
    else:
        bgdrat = (
            (1. - aminrl / varat_3_iel) * (varat_1_iel - varat_2_iel) +
            varat_2_iel)
    return bgdrat


def esched_point(return_type):
    """Calculate flow of an element accompanying decomposition of C.

    Calculate the movement of one element (N or P) as C decomposes from one
    state variable (the donating stock, or box A) to another state variable
    (the receiving stock, or box B).  Esched.f

    Parameters:
        return_type (string): flag indicating whether to return material
            leaving box A, material arriving in box B, or material flowing
            into or out of the mineral pool

    Returns:
        the function `_esched`

    """
    def _esched(cflow, tca, rcetob, anps, labile):
        """Calculate the flow of one element to accompany decomp of C.

        This is a transcription of Esched.f: "Schedule N, P, or S flow and
        associated mineralization or immobilization flow for decomposition
        from Box A to Box B."
        If there is enough of iel (N or P) in the donating stock to satisfy
        the required ratio, that material flows from the donating stock to
        the receiving stock and whatever iel is leftover goes to mineral
        pool. If there is not enough iel to satisfy the required ratio, iel
        is drawn from the mineral pool to satisfy the ratio; if there is
        not enough iel in the mineral pool, the material does not leave the
        donating stock.

        Parameters:
            cflow: total C that is decomposing from box A to box B
            tca: C in donating stock, i.e. box A
            rcetob: required ratio of C/iel in the receiving stock
            anps: iel (N or P) in the donating stock
            labile: mineral iel (N or P)

        Returns:
            material_leaving_a, the amount of material leaving box A, if
                return_type is 'material_leaving_a'
            material_arriving_b, the amount of material arriving in box B,
                if return_type is 'material_arriving_b'
            mnrflo, flow in or out of mineral pool, if return_type is
                'mineral_flow'

        """
        outofa = anps * (cflow/tca)
        if (cflow/outofa > rcetob):
            # immobilization occurs
            immflo = cflow/rcetob - outofa
            if ((labile - immflo) > 0):
                material_leaving_a = outofa  # outofa flows from anps to bnps
                material_arriving_b = outofa + immflo
                mnrflo = -immflo  # immflo flows from mineral to bnps
            else:
                mnrflo = 0  # no flow from box A to B, nothing moves
                material_leaving_a = 0
                material_arriving_b = 0
        else:
            # mineralization
            atob = cflow/rcetob
            material_leaving_a = outofa
            material_arriving_b = atob  # atob flows from anps to bnps
            mnrflo = outofa - atob  # the rest of material leaving box A
                                    # goes to mineral
        if return_type == 'material_leaving_a':
            return material_leaving_a
        elif return_type == 'material_arriving_b':
            return material_arriving_b
        elif return_type == 'mineral_flow':
            return mnrflo
    return _esched


def declig_point(return_type):
    """Point implementation of decomposition of structural material.

    Track the decomposition of structural material (i.e., material containing
    lignin) into SOM2 and SOM1.

    Returns:
        the function `_declig`

    """
    def _declig(
            aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr, tcflow,
            struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
            rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2):
        """Decomposition of material containing lignin into SOM2 and SOM1.

        This function is called when surface structural C (STRUCC_1)
        decomposes, and again when soil structural C (STRUCC_2) decomposes.
        Declig.f

        Parameters:
            aminrl_1: mineral N averaged across the 4-times-per-monthly
                decomposition timesteps
            aminrl_2: mineral P averaged across the 4-times-per-monthly
                decomposition timesteps
            ligcon: lignin content of the decomposing material
            rsplig: co2 loss with decomposition to SOM2
            ps1co2_lyr: co2 loss with decomposition to SOM1
            strucc_lyr: structural C in lyr that is decomposing
            tcflow: the total amount of C flowing out of strucc_lyr
            struce_lyr_1: N in structural material in the layer that is
                decomposing
            struce_lyr_2: P in structural material in the layer that is
                decomposing
            rnew_lyr_1_1: required C/N ratio of material decomposing to SOM1
            rnew_lyr_2_1: required C/P ratio of material decomposing to SOM1
            rnew_lyr_1_2: required C/N ratio of material decomposing to SOM2
            rnew_lyr_2_2: required C/P ratio of material decomposing to SOM2
            minerl_1_1: surface mineral N
            minerl_1_2: surface mineral P

        Returns:
            The change in one state variable, where the state variable is
                specified by return_type:
                d_strucc_lyr, change in C in the decomposing layer, if
                    return_type is 'd_strucc'
                d_struce_lyr_1, change in N in the decomposing lyr, if
                    return_type is 'd_struce_1'
                d_struce_lyr_2, change in P in the decomposing lyr, if
                    return_type is 'd_struce_2'
                d_minerl_1_1, change in surface mineral N, if return_type is
                    'd_minerl_1_1'
                d_minerl_1_2, change in surface mineral P, if return_type is
                    'd_minerl_1_2'
                d_gromin_1, change in gross N mineralization, if return_type is
                    'd_gromin_1'
                d_som2c_lyr, change in C in SOM2, if return_type is 'd_som2c'
                d_som2e_lyr_1, change in N in SOM2, if return_type is
                    'd_som2e_1'
                d_som2e_lyr_2, change in P in SOM2, if return_type is
                    'd_som2e_2'
                d_som1c_lyr, change in C in SOM1, if return_type is 'd_som1c'
                d_som1e_lyr_1, change in N in SOM1, if return_type is
                    'd_som1e_1'
                d_som1e_lyr_2, change in P in SOM1, if return_type is
                    'd_som1e_2'

        """
        # initialize change (delta, d) in state variables
        d_strucc_lyr = 0  # change in structural C in decomposing lyr
        d_struce_lyr_1 = 0  # change in structural N in decomposing lyr
        d_struce_lyr_2 = 0  # change in structural P in decomposing lyr
        d_minerl_1_1 = 0  # change in surface mineral N
        d_minerl_1_2 = 0  # change in surface mineral P
        d_gromin_1 = 0  # change in gross N mineralization
        d_som2c_lyr = 0  # change in C in SOM2 in lyr
        d_som2e_lyr_1 = 0  # change in N in SOM2 in lyr
        d_som2e_lyr_2 = 0  # change in P in SOM2 in lyr
        d_som1c_lyr = 0  # change in C in SOM1 in lyr
        d_som1e_lyr_1 = 0  # change in N in SOM1 in lyr
        d_som1e_lyr_2 = 0  # change in P in SOM1 in lyr

        decompose_mask = (
            ((aminrl_1 > 0.0000001) | (
                (strucc_lyr / struce_lyr_1) <= rnew_lyr_1_1)) &
            ((aminrl_2 > 0.0000001) | (
                (strucc_lyr / struce_lyr_2) <= rnew_lyr_2_1)))

        if decompose_mask:
            d_strucc_lyr = -tcflow
            # material decomposes first to som2
            tosom2 = tcflow * ligcon  # line 127 Declig.f

            # respiration associated with decomposition to som2
            co2los = tosom2 * rsplig  # line 130 Declig.f
            mnrflo_1 = co2los * struce_lyr_1 / strucc_lyr  # line 132
            d_struce_lyr_1 -= mnrflo_1
            d_minerl_1_1 += mnrflo_1
            if mnrflo_1 > 0:
                d_gromin_1 += mnrflo_1
            mnrflo_2 = co2los * struce_lyr_2 / strucc_lyr
            d_struce_lyr_2 -= mnrflo_2
            d_minerl_1_2 += mnrflo_2

            net_tosom2 = tosom2 - co2los  # line 136 Declig.f
            d_som2c_lyr += net_tosom2  # line 140 Declig.f

            # N and P flows from struce_lyr to som2e_lyr, line 145 Declig.f
            # N first
            material_leaving_a = esched_point(
                'material_leaving_a')(
                    net_tosom2, strucc_lyr, rnew_lyr_1_2, struce_lyr_1,
                    minerl_1_1)
            material_arriving_b = esched_point(
                'material_arriving_b')(
                    net_tosom2, strucc_lyr, rnew_lyr_1_2, struce_lyr_1,
                    minerl_1_1)
            mineral_flow = esched_point(
                'mineral_flow')(
                    net_tosom2, strucc_lyr, rnew_lyr_1_2, struce_lyr_1,
                    minerl_1_1)
            # schedule flows
            d_struce_lyr_1 -= material_leaving_a
            d_som2e_lyr_1 += material_arriving_b
            d_minerl_1_1 += mineral_flow
            if mineral_flow > 0:
                d_gromin_1 += mineral_flow

            # P second
            material_leaving_a = esched_point(
                'material_leaving_a')(
                    net_tosom2, strucc_lyr, rnew_lyr_2_2, struce_lyr_2,
                    minerl_1_2)
            material_arriving_b = esched_point(
                'material_arriving_b')(
                    net_tosom2, strucc_lyr, rnew_lyr_2_2, struce_lyr_2,
                    minerl_1_2)
            mineral_flow = esched_point(
                'mineral_flow')(
                    net_tosom2, strucc_lyr, rnew_lyr_2_2, struce_lyr_2,
                    minerl_1_2)
            # schedule flows
            d_struce_lyr_2 -= material_leaving_a
            d_som2e_lyr_2 += material_arriving_b
            d_minerl_1_2 += mineral_flow

            # what's left decomposes to som1
            tosom1 = tcflow - tosom2  # line 160 Declig.f
            co2los = tosom1 * ps1co2_lyr  # line 163 Declig.f

            # respiration associated with decomposition to som1
            mnrflo_1 = co2los * struce_lyr_1 / strucc_lyr  # line 165
            d_struce_lyr_1 -= mnrflo_1
            d_minerl_1_1 += mnrflo_1
            if mnrflo_1 > 0:
                d_gromin_1 += mnrflo_1
            mnrflo_2 = co2los * struce_lyr_2 / strucc_lyr
            d_struce_lyr_2 -= mnrflo_2
            d_minerl_1_2 += mnrflo_2

            net_tosom1 = tosom1 - co2los  # line 169 Declig.f
            d_som1c_lyr += net_tosom1  # line 173 Declig.f

            # N and P flows from struce_lyr to som1e_lyr, line 178 Declig.f
            # N first
            material_leaving_a = esched_point(
                'material_leaving_a')(
                    net_tosom1, strucc_lyr, rnew_lyr_1_1, struce_lyr_1,
                    minerl_1_1)
            material_arriving_b = esched_point(
                'material_arriving_b')(
                    net_tosom1, strucc_lyr, rnew_lyr_1_1, struce_lyr_1,
                    minerl_1_1)
            mineral_flow = esched_point(
                'mineral_flow')(
                    net_tosom1, strucc_lyr, rnew_lyr_1_1, struce_lyr_1,
                    minerl_1_1)
            # schedule flows
            d_struce_lyr_1 -= material_leaving_a
            d_som1e_lyr_1 += material_arriving_b
            d_minerl_1_1 += mineral_flow
            if mineral_flow > 0:
                d_gromin_1 += mineral_flow

            # P
            material_leaving_a = esched_point(
                'material_leaving_a')(
                    net_tosom1, strucc_lyr, rnew_lyr_2_1, struce_lyr_2,
                    minerl_1_2)
            material_arriving_b = esched_point(
                'material_arriving_b')(
                    net_tosom1, strucc_lyr, rnew_lyr_2_1, struce_lyr_2,
                    minerl_1_2)
            mineral_flow = esched_point(
                'mineral_flow')(
                    net_tosom1, strucc_lyr, rnew_lyr_2_1, struce_lyr_2,
                    minerl_1_2)
            # schedule flows
            d_struce_lyr_2 -= material_leaving_a
            d_som1e_lyr_2 += material_arriving_b
            d_minerl_1_2 += mineral_flow

        if return_type == 'd_strucc':
            return d_strucc_lyr
        elif return_type == 'd_struce_1':
            return d_struce_lyr_1
        elif return_type == 'd_struce_2':
            return d_struce_lyr_2
        elif return_type == 'd_minerl_1_1':
            return d_minerl_1_1
        elif return_type == 'd_minerl_1_2':
            return d_minerl_1_2
        elif return_type == 'd_gromin_1':
            return d_gromin_1
        elif return_type == 'd_som2c':
            return d_som2c_lyr
        elif return_type == 'd_som2e_1':
            return d_som2e_lyr_1
        elif return_type == 'd_som2e_2':
            return d_som2e_lyr_2
        elif return_type == 'd_som1c':
            return d_som1c_lyr
        elif return_type == 'd_som1e_1':
            return d_som1e_lyr_1
        elif return_type == 'd_som1e_2':
            return d_som1e_lyr_2
    return _declig


def agdrat_point(anps, tca, pcemic_1_iel, pcemic_2_iel, pcemic_3_iel):
    """Point implementation of `Agdrat.f`.

    Calculate the C/<iel> ratio of new material that is the result of
    decomposition into "box B".

    Parameters:
        anps: <iel> (N or P) in the decomposing stock
        tca: total C in the decomposing stock
        pcemic_1_iel: maximum C/<iel> of new SOM1
        pcemic_2_iel: minimum C/<iel> of new SOM1
        pcemic_3_iel: minimum <iel> content of decomposing material that gives
            minimum C/<iel> of new material

    Returns:
        agdrat, the C/<iel> ratio of new material

    """
    cemicb = (pcemic_2_iel - pcemic_1_iel) / pcemic_3_iel
    if ((tca * 2.5) <= 0.0000000001):
        econt = 0
    else:
        econt = anps / (tca * 2.5)
    if econt > pcemic_3_iel:
        agdrat = pcemic_2_iel
    else:
        agdrat = pcemic_1_iel + econt * cemicb
    return agdrat


def fsfunc_point(minerl_1_2, pslsrb, sorpmx):
    """Calculate the fraction of mineral P that is in solution.

    The fraction of P in solution is influenced by two soil properties:
    the maximum sorption potential of the soil and sorption affinity.

    Parameters:
        minerl_1_2 (float): state variable, surface mineral P
        pslsrb (float): parameter, P sorption affinity
        sorpmx (float): parameter, maximum P sorption of the soil

    Returns:
        fsol, fraction of P in solution

    """
    if minerl_1_2 == 0:
        return 0
    c = sorpmx * (2. - pslsrb) / 2.
    b = sorpmx - minerl_1_2 + c
    labile = (-b + numpy.sqrt(b * b + 4 * c * minerl_1_2)) / 2.
    fsol = labile / minerl_1_2
    return fsol


def calc_nutrient_limitation_point(
        potenc, rtsh, eavail_1, eavail_2, snfxmx_1,
        cerat_max_above_1, cerat_max_below_1, cerat_max_above_2,
        cerat_max_below_2, cerat_min_above_1, cerat_min_below_1,
        cerat_min_above_2, cerat_min_below_2):
    """Calculate C, N and P in new production given nutrient availability.

    Point-based implementation of `calc_nutrient_limitation`, Nutrlm.f.

    Parameters:
        potenc (float): potential production of C calculated by root:shoot
            ratio submodel. remember this is tgprod_pot_prod / 2.5
        rtsh (float): root/shoot ratio
        eavail_1: available N calculated by _calc_available_nutrient()
            (includes predicted N fixation)
        eavail_2: available P calculated by _calc_available_nutrient()
        snfxmx_1 (float): parameter, maximum symbiotic N fixation rate
        cerat_max_above_1 (cercrp from Growth.f): max C/N ratio of new
            aboveground growth, calculated once per model timestep
        cerat_max_below_1: max C/N ratio of new belowground growth,
            calculated once per model timestep
        cerat_max_above_2 (cercrp from Growth.f): max C/P ratio of new
            aboveground growth, calculated once per model timestep
        cerat_max_below_2: max C/P ratio of new belowground growth,
            calculated once per model timestep
        cerat_min_above_1 (cercrp from Growth.f): min C/N ratio of new
            aboveground growth, calculated once per model timestep
        cerat_min_below_1: min C/N ratio of new belowground growth,
            calculated once per model timestep
        cerat_min_above_2 (cercrp from Growth.f): min C/P ratio of new
            aboveground growth, calculated once per model timestep
        cerat_min_below_2: min C/P ratio of new belowground growth,
            calculated once per model timestep

    Returns:
        a dictionary of values indexed by the following keys:
            'c_production', total C production limited by nutrient
                availability
            'eup_above_1', N in new aboveground production
            'eup_below_1', N in new belowground production
            'eup_above_2', P in new aboveground production
            'eup_below_2', P in new belowground production
            'plantNfix', N fixation that actually occurs

    """
    cfrac_below = rtsh / (rtsh + 1.)
    cfrac_above = 1. - cfrac_below

    # min/max eci is indexed to aboveground only or belowground only
    maxeci_above_1 = 1. / cerat_min_above_1
    mineci_above_1 = 1. / cerat_max_above_1
    maxeci_below_1 = 1. / cerat_min_below_1
    mineci_below_1 = 1. / cerat_max_below_1

    maxeci_above_2 = 1. / cerat_min_above_2
    mineci_above_2 = 1. / cerat_max_above_2
    maxeci_below_2 = 1. / cerat_min_below_2
    mineci_below_2 = 1. / cerat_max_below_2

    # maxec is average e/c ratio across aboveground and belowground
    maxec_1 = cfrac_below * maxeci_below_1 + cfrac_above * maxeci_above_1
    maxec_2 = cfrac_below * maxeci_below_2 + cfrac_above * maxeci_above_2

    # calculate cpbe_1, N/C ratio according to demand and supply
    demand_1 = potenc * maxec_1
    if eavail_1 > demand_1:
        # if supply is sufficient, E/C ratio of new production is the max
        # demanded
        ecfor_above_1 = maxeci_above_1  # line 75
        ecfor_below_1 = maxeci_below_1
    else:
        # supply is insufficient; E/C ratio of new production is
        # proportional to the ratio of supply to demand
        ecfor_above_1 = (
            mineci_above_1 +
            (maxeci_above_1 - mineci_above_1) *
            eavail_1 / demand_1)
        ecfor_below_1 = (
            mineci_below_1 +
            (maxeci_below_1 - mineci_below_1) *
            eavail_1 / demand_1)
    cpbe_1 = cfrac_below * ecfor_below_1 + cfrac_above * ecfor_above_1
    c_constrained_1 = eavail_1 / cpbe_1  # C constrained by N

    # calculate cpbe_2, P/C ratio according to demand and supply
    demand_2 = potenc * maxec_2
    if eavail_2 > demand_2:
        # if supply is sufficient, E/C ratio of new production is the max
        # demanded
        ecfor_above_2 = maxeci_above_2  # line 75
        ecfor_below_2 = maxeci_below_2
    else:
        # supply is insufficient; E/C ratio of new production is
        # proportional to the ratio of supply to demand
        ecfor_above_2 = (
            mineci_above_2 +
            (maxeci_above_2 - mineci_above_2) *
            eavail_2 / demand_2)
        ecfor_below_2 = (
            mineci_below_2 +
            (maxeci_below_2 - mineci_below_2) *
            eavail_2 / demand_2)
    cpbe_2 = cfrac_below * ecfor_below_2 + cfrac_above * ecfor_above_2
    c_constrained_2 = eavail_2 / cpbe_2  # C constrained by P

    # C production limited by nutrient availability
    cprodl = min(potenc, c_constrained_1, c_constrained_2)
    # calculate N and P in new production; this will be taken up from
    # soil mineral content and crop storage
    # lines 214-223 Nutrlm.f
    eup_above_1 = cprodl * cfrac_above * ecfor_above_1
    eup_below_1 = cprodl * cfrac_below * ecfor_below_1
    eprodl_1 = eup_above_1 + eup_below_1

    eup_above_2 = cprodl * cfrac_above * ecfor_above_2
    eup_below_2 = cprodl * cfrac_below * ecfor_below_2

    # "prevent precision error" line 235 Nutrlm.f
    maxNfix = snfxmx_1 * cprodl
    if (eprodl_1 - (eavail_1 + maxNfix) > 0.05):
        eprodl_1 = eavail_1 + maxNfix
    plantNfix = max(eprodl_1 - eavail_1, 0.)

    result_dict = {
        'c_production': cprodl,
        'eup_above_1': eup_above_1,
        'eup_below_1': eup_below_1,
        'eup_above_2': eup_above_2,
        'eup_below_2': eup_below_2,
        'plantNfix': plantNfix,
    }
    return result_dict


def nutrient_uptake_point(
        iel, nlay, availm, eavail_iel, pft_percent_cover, eup_above_iel,
        eup_below_iel, storage_iel, plantNfix, pslsrb, sorpmx, aglive_iel,
        bglive_iel, minerl_dict):
    """Calculate flow of nutrients during plant growth.

    Given the N or P predicted to flow into new above- and belowground
    production, calculate how much of that nutrient will be taken from the crop
    storage pool and how much will be taken from soil.  For N, some of the
    necessary uptake also comes from N fixation performed by the plant.
    N and P taken up from the soil by one plant functional type are weighted by
    the percent cover of that functional type.
    Lines 124-156, Restrp.f, lines 186-226 Growth.f

    Parameters:
        iel (int): index identifying N or P
        nlay (int): number of soil layers accessible to this plant functional
            type
        availm (float): total available mineral in soil layers accessible to
            this plant functional type
        eavail_iel (float): available iel calculated by
            _calc_available_nutrient()
        pft_percent_cover (float): percent cover of this plant functional type
        eup_above_iel (float): iel to be allocated to new aboveground
            production
        eup_below_iel (float_: iel to be allocated to new belowground
            production
        storage_iel: state variable, crpstg_iel
        plantNfix (float): symbiotic N fixed by this plant functional type
            (calculated in `calc_nutrient_limitation`)
        pslsrb (float): parameter, P sorption affinity
        sorpmx (float): parameter, maximum P sorption of the soil
        aglive_iel: state variable, iel in aboveground live biomass
        bglive_iel: state variable, iel in belowground live biomass
        minerl_dict (dict): dictionary of of state variables:
            minerl_1_iel: state variable, iel in soil layer 1
            minerl_2_iel: state variable, iel in soil layer 2
            minerl_3_iel: state variable, iel in soil layer 3
            minerl_4_iel: state variable, iel in soil layer 4
            minerl_5_iel: state variable, iel in soil layer 5
            minerl_6_iel: state variable, iel in soil layer 6
            minerl_7_iel: state variable, iel in soil layer 7

    Returns:
        dictionary of values indexed by the following keys:
            delta_aglive_iel: change in iel in aboveground live biomass
            aglive_iel: ending iel in aboveground live biomass
            bglive_iel: modified iel in belowground live biomass
            storage_iel: modified iel in crop storage
            minerl_1_iel: modified iel in soil layer 1
            minerl_2_iel: modified iel in soil layer 2
            minerl_3_iel: modified iel in soil layer 3
            minerl_4_iel: modified iel in soil layer 4
            minerl_5_iel: modified iel in soil layer 5
            minerl_6_iel: modified iel in soil layer 6
            minerl_7_iel: modified iel in soil layer 7

    """
    delta_aglive_iel = 0
    eprodl_iel = eup_above_iel + eup_below_iel
    if eprodl_iel < storage_iel:
        uptake_storage = eprodl_iel
        uptake_soil = 0
    else:
        uptake_storage = storage_iel
        if iel == 1:
            uptake_soil = min(
                (eprodl_iel - storage_iel - plantNfix),
                (eavail_iel - storage_iel - plantNfix))
            uptake_Nfix = plantNfix
        else:
            uptake_soil = eprodl_iel - storage_iel

    # uptake from crop storage into aboveground and belowground live
    if storage_iel > 0:
        storage_iel = storage_iel - uptake_storage
        uptake_storage_above = uptake_storage * (eup_above_iel / eprodl_iel)
        uptake_storage_below = uptake_storage * (eup_below_iel / eprodl_iel)
        delta_aglive_iel = delta_aglive_iel + uptake_storage_above
        bglive_iel = bglive_iel + uptake_storage_below

    # uptake from each soil layer in proportion to its contribution to availm
    minerl_dict_copy = minerl_dict.copy()
    for lyr in range(1, nlay + 1):
        if minerl_dict['minerl_{}_iel'.format(lyr)] > 0:
            if iel == 2:
                fsol = fsfunc_point(
                    minerl_dict['minerl_1_iel'], pslsrb, sorpmx)
            else:
                fsol = 1.
            minerl_uptake_lyr = (
                uptake_soil * minerl_dict['minerl_{}_iel'.format(lyr)] * fsol /
                availm)
            minerl_dict_copy['minerl_{}_iel'.format(lyr)] = (
                minerl_dict['minerl_{}_iel'.format(lyr)] -
                (minerl_uptake_lyr * pft_percent_cover))
            uptake_minerl_lyr_above = (
                minerl_uptake_lyr * (eup_above_iel / eprodl_iel))
            uptake_minerl_lyr_below = (
                minerl_uptake_lyr * (eup_below_iel / eprodl_iel))
            delta_aglive_iel = delta_aglive_iel + uptake_minerl_lyr_above
            bglive_iel = bglive_iel + uptake_minerl_lyr_below

    # uptake from N fixation
    if (iel == 1) & (plantNfix > 0):
        uptake_Nfix_above = uptake_Nfix * (eup_above_iel / eprodl_iel)
        uptake_Nfix_below = uptake_Nfix * (eup_below_iel / eprodl_iel)
        delta_aglive_iel = delta_aglive_iel + uptake_Nfix_above
        bglive_iel = bglive_iel + uptake_Nfix_below
    result_dict = {
        'delta_aglive_iel': delta_aglive_iel,
        'aglive_iel': aglive_iel,
        'bglive_iel': bglive_iel,
        'storage_iel': storage_iel,
        'minerl_1_iel': minerl_dict_copy['minerl_1_iel'],
        'minerl_2_iel': minerl_dict_copy['minerl_2_iel'],
        'minerl_3_iel': minerl_dict_copy['minerl_3_iel'],
        'minerl_4_iel': minerl_dict_copy['minerl_4_iel'],
        'minerl_5_iel': minerl_dict_copy['minerl_5_iel'],
        'minerl_6_iel': minerl_dict_copy['minerl_6_iel'],
        'minerl_7_iel': minerl_dict_copy['minerl_7_iel'],
    }
    return result_dict


class foragetests(unittest.TestCase):
    """Regression tests for InVEST forage model."""

    def setUp(self):
        """Create temporary workspace directory."""
        self.workspace_dir = "C:/Users/ginge/Desktop/temp_test_dir"
        os.makedirs(self.workspace_dir)
        global PROCESSING_DIR
        PROCESSING_DIR = os.path.join(self.workspace_dir, "temporary_files")
        os.makedirs(PROCESSING_DIR)

    def tearDown(self):
        """Clean up remaining files."""
        shutil.rmtree(self.workspace_dir)

    @staticmethod
    def generate_base_args(workspace_dir):
        """Generate a base sample args dict for forage model."""
        args = {
            'workspace_dir': workspace_dir,
            'results_suffix': "",
            'starting_month': 1,
            'starting_year': 2016,
            'n_months': 2,
            'aoi_path': os.path.join(
                SAMPLE_DATA, 'soums_monitoring_area_diss.shp'),
            'management_threshold': 2000,
            'proportion_legume_path': os.path.join(
                SAMPLE_DATA, 'prop_legume.tif'),
            'bulk_density_path': os.path.join(
                SAMPLE_DATA, 'soil', 'bulkd.tif'),
            'ph_path': os.path.join(
                SAMPLE_DATA, 'soil', 'pH.tif'),
            'clay_proportion_path': os.path.join(
                SAMPLE_DATA, 'soil', 'clay.tif'),
            'silt_proportion_path': os.path.join(
                SAMPLE_DATA, 'soil', 'silt.tif'),
            'sand_proportion_path': os.path.join(
                SAMPLE_DATA, 'soil', 'sand.tif'),
            'monthly_precip_path_pattern': os.path.join(
                SAMPLE_DATA, 'CHIRPS_div_by_10',
                'chirps-v2.0.<year>.<month>.tif'),
            'min_temp_path_pattern': os.path.join(
                SAMPLE_DATA, 'temp', 'wc2.0_30s_tmin_<month>.tif'),
            'max_temp_path_pattern': os.path.join(
                SAMPLE_DATA, 'temp', 'wcs2.0_30s_tmax_<month>.tif'),
            'monthly_vi_path_pattern': os.path.join(
                SAMPLE_DATA, 'NDVI', 'ndvi_<year>_<month>.tif'),
            'site_param_table': os.path.join(
                SAMPLE_DATA, 'site_parameters.csv'),
            'site_param_spatial_index_path': os.path.join(
                SAMPLE_DATA, 'site_index.tif'),
            'veg_trait_path': os.path.join(SAMPLE_DATA, 'pft_trait.csv'),
            'veg_spatial_composition_path_pattern': os.path.join(
                SAMPLE_DATA, 'pft<PFT>.tif'),
            'animal_trait_path': os.path.join(
                SAMPLE_DATA, 'animal_trait_table.csv'),
            'animal_grazing_areas_path': os.path.join(
                SAMPLE_DATA, 'sfu_per_soum.shp'),
            'site_initial_table': os.path.join(
                SAMPLE_DATA, 'site_initial_table.csv'),
            'pft_initial_table': os.path.join(
                SAMPLE_DATA, 'pft_initial_table.csv'),
        }
        return args

    def assert_all_values_in_raster_within_range(
            self, raster_to_test, minimum_acceptable_value,
            maximum_acceptable_value, nodata_value):
        """Test that `raster_to_test` contains values within acceptable range.

        The values within `raster_to_test` that are not null must be
        greater than or equal to `minimum_acceptable_value` and
        less than or equal to `maximum_acceptable_value`.

        Raises:
            AssertionError if values are outside acceptable range

        Returns:
            None

        """
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (raster_to_test, 1)):
            if len(raster_block[raster_block != nodata_value]) == 0:
                continue
            min_val = numpy.amin(
                raster_block[raster_block != nodata_value])
            self.assertGreaterEqual(
                min_val, minimum_acceptable_value,
                msg="Raster contains values smaller than acceptable "
                + "minimum: {}, {} (acceptable min: {})".format(
                    raster_to_test, min_val, minimum_acceptable_value))
            max_val = numpy.amax(
                raster_block[raster_block != nodata_value])
            self.assertLessEqual(
                max_val, maximum_acceptable_value,
                msg="Raster contains values larger than acceptable "
                + "maximum: {}, {} (acceptable max: {})".format(
                    raster_to_test, max_val, maximum_acceptable_value))

    def assert_all_values_in_array_within_range(
            self, array_to_test, minimum_acceptable_value,
            maximum_acceptable_value, nodata_value):
        """Test that `array_to_test` contains values within acceptable range.

        The values within `array_to_test` that are not null must be
        greater than or equal to `minimum_acceptable_value` and
        less than or equal to `maximum_acceptable_value`.

        Raises:
            AssertionError if values are outside acceptable range

        Returns:
            None

        """
        if len(array_to_test[array_to_test != nodata_value]) == 0:
            return
        min_val = numpy.amin(
            array_to_test[array_to_test != nodata_value])
        self.assertGreaterEqual(
            min_val, minimum_acceptable_value,
            msg="Array contains values smaller than acceptable minimum: " +
            "min value: {}, acceptable min: {}".format(
                min_val, minimum_acceptable_value))
        max_val = numpy.amax(
            array_to_test[array_to_test != nodata_value])
        self.assertLessEqual(
            max_val, maximum_acceptable_value,
            msg="Array contains values larger than acceptable maximum: " +
            "max value: {}, acceptable max: {}".format(
                max_val, maximum_acceptable_value))

    def assert_sorted_lists_equal(self, string_list_1, string_list_2):
        """Test that `string_list_1` and `string_list_2` are equal.

        Test that two lists of strings contain the same strings in the same
        order.

        Raises:
            AssertionError if the number of items in string_list_1 is not equal
                to the number of items in string_list_2, or if the order of
                elements differs between string_list_1 and string_list_2.

        Returns:
            None

        """
        self.assertEqual(len(string_list_1), len(string_list_2))
        for i in range(len(string_list_1)):
            self.assertEqual(string_list_1[i], string_list_2[i])

    @unittest.skip("did not run the whole model, running unit tests only")
    def test_model_runs(self):
        """Test forage model."""
        from rangeland_production import forage

        if not os.path.exists(SAMPLE_DATA):
            self.fail(
                "Sample input directory not found at %s" % SAMPLE_DATA)

        args = foragetests.generate_base_args(self.workspace_dir)
        forage.execute(args)

    def test_shortwave_radiation(self):
        """Test `_shortwave radiation`.

        Use one set of inputs, including a raster with known latitude, to test
        the function `_shortwave radiation` against a result calculated by
        hand.

        Raises:
            AssertionError if the raster created by `_shortwave_radiation`
                contains more than one unique value
            AssertionError if the value returned by `_shortwave_radiation' is
                not within 0.01 of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        fill_value = 0
        template_raster = os.path.join(
            self.workspace_dir, 'template_raster.tif')

        create_constant_raster(template_raster, fill_value)

        month = 5
        shwave_path = os.path.join(self.workspace_dir, 'shwave.tif')
        forage._shortwave_radiation(template_raster, month, shwave_path)

        # assert the value in the raster `shwave_path` is equal to value
        # calculated by hand
        result_set = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (shwave_path, 1)):
            result_set.update(numpy.unique(raster_block))
        self.assertEqual(
            len(result_set), 1,
            msg="One unique value expected in shortwave radiation raster")
        test_result = list(result_set)[0]
        self.assertAlmostEqual(
            test_result, 990.7401, delta=0.01,
            msg="Test result does not match expected value")

    def test_calc_ompc(self):
        """Test `_calc_ompc`.

        Use one set of inputs to test the estimation of total organic
        matter against a result calculated by hand.

        Raises:
            AssertionError if the raster created by `_calc_ompc`
                contains more than one unique value
            AssertionError if the value returned by `_calc_ompc' is
                not within 0.0001 of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        som1c_2_path = os.path.join(self.workspace_dir, 'som1c_2.tif')
        som2c_2_path = os.path.join(self.workspace_dir, 'som2c_2.tif')
        som3c_path = os.path.join(self.workspace_dir, 'som3c.tif')
        bulk_d_path = os.path.join(self.workspace_dir, 'bulkd.tif')
        edepth_path = os.path.join(self.workspace_dir, 'edepth.tif')

        create_constant_raster(som1c_2_path, 42.109)
        create_constant_raster(som2c_2_path, 959.1091)
        create_constant_raster(som3c_path, 588.0574)
        create_constant_raster(bulk_d_path, 1.5)
        create_constant_raster(edepth_path, 0.2)

        ompc_path = os.path.join(self.workspace_dir, 'ompc.tif')

        forage._calc_ompc(
            som1c_2_path, som2c_2_path, som3c_path, bulk_d_path, edepth_path,
            ompc_path)

        # assert the value in the raster `ompc_path` is equal to value
        # calculated by hand
        result_set = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (ompc_path, 1)):
            result_set.update(numpy.unique(raster_block))
        self.assertEqual(
            len(result_set), 1,
            msg="One unique value expected in organic matter raster")
        test_result = list(result_set)[0]
        self.assertAlmostEqual(
            test_result, 0.913304, delta=0.0001,
            msg="Test result does not match expected value")

    def test_calc_afiel(self):
        """Test `_calc_afiel`.

        Use one set of inputs to test the estimation of field capacity against
        a result calculated by hand.

        Raises:
            AssertionError if the raster created by `_calc_afiel`
                contains more than one unique value
            AssertionError if the value returned by `_calc_afiel' is
                not within 0.0001 of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        sand_path = os.path.join(self.workspace_dir, 'sand.tif')
        silt_path = os.path.join(self.workspace_dir, 'silt.tif')
        clay_path = os.path.join(self.workspace_dir, 'clay.tif')
        ompc_path = os.path.join(self.workspace_dir, 'ompc.tif')
        bulkd_path = os.path.join(self.workspace_dir, 'bulkd.tif')

        create_constant_raster(sand_path, 0.39)
        create_constant_raster(silt_path, 0.41)
        create_constant_raster(clay_path, 0.2)
        create_constant_raster(ompc_path, 0.913304)
        create_constant_raster(bulkd_path, 1.5)

        afiel_path = os.path.join(self.workspace_dir, 'afiel.tif')

        forage._calc_afiel(
            sand_path, silt_path, clay_path, ompc_path, bulkd_path, afiel_path)

        # assert the value in the raster `afiel_path` is equal to value
        # calculated by hand
        result_set = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (afiel_path, 1)):
            result_set.update(numpy.unique(raster_block))
        self.assertEqual(
            len(result_set), 1,
            msg="One unique value expected in field capacity raster")
        test_result = list(result_set)[0]
        self.assertAlmostEqual(
            test_result, 0.30895, delta=0.0001,
            msg="Test result does not match expected value")

    def test_calc_awilt(self):
        """Test `_calc_awilt`.

        Use one set of inputs to test the estimation of wilting point against
        a result calculated by hand.

        Raises:
            AssertionError if the raster created by `_calc_awilt`
                contains more than one unique value
            AssertionError if the value returned by `_calc_awilt' is
                not within 0.0001 of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        sand_path = os.path.join(self.workspace_dir, 'sand.tif')
        silt_path = os.path.join(self.workspace_dir, 'silt.tif')
        clay_path = os.path.join(self.workspace_dir, 'clay.tif')
        ompc_path = os.path.join(self.workspace_dir, 'ompc.tif')
        bulkd_path = os.path.join(self.workspace_dir, 'bulkd.tif')

        create_constant_raster(sand_path, 0.39)
        create_constant_raster(silt_path, 0.41)
        create_constant_raster(clay_path, 0.2)
        create_constant_raster(ompc_path, 0.913304)
        create_constant_raster(bulkd_path, 1.5)

        awilt_path = os.path.join(self.workspace_dir, 'awilt.tif')

        forage._calc_awilt(
            sand_path, silt_path, clay_path, ompc_path, bulkd_path, awilt_path)

        # assert the value in the raster `awilt_path` is equal to value
        # calculated by hand
        result_set = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (awilt_path, 1)):
            result_set.update(numpy.unique(raster_block))
        self.assertEqual(
            len(result_set), 1,
            msg="One unique value expected in wilting point raster")
        test_result = list(result_set)[0]
        self.assertAlmostEqual(
            test_result, 0.201988, delta=0.0001,
            msg="Test result does not match expected value")

    def test_afiel_awilt(self):
        """Test `_afiel_awilt`.

        Use the function `_afiel_awilt` to calculate field capacity and wilting
        point from randomly generated inputs. Test that calculated field
        capacity and calculated wilting point are in the range [0.01, 0.9].
        Introduce nodata values into the input rasters and test that calculated
        field capacity and wilting point remain in the range [0.01, 0.9].
        Test the function with known values against results calculated by hand.

        Raises:
            AssertionError if a result from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if a result from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        site_param_table = {1: {'edepth': 0.2}}
        pp_reg = {
            'afiel_1_path': os.path.join(self.workspace_dir, 'afiel_1.tif'),
            'afiel_2_path': os.path.join(self.workspace_dir, 'afiel_2.tif'),
            'afiel_3_path': os.path.join(self.workspace_dir, 'afiel_3.tif'),
            'afiel_4_path': os.path.join(self.workspace_dir, 'afiel_4.tif'),
            'afiel_5_path': os.path.join(self.workspace_dir, 'afiel_5.tif'),
            'afiel_6_path': os.path.join(self.workspace_dir, 'afiel_6.tif'),
            'afiel_7_path': os.path.join(self.workspace_dir, 'afiel_7.tif'),
            'afiel_8_path': os.path.join(self.workspace_dir, 'afiel_8.tif'),
            'afiel_9_path': os.path.join(self.workspace_dir, 'afiel_9.tif'),
            'awilt_1_path': os.path.join(self.workspace_dir, 'awilt_1.tif'),
            'awilt_2_path': os.path.join(self.workspace_dir, 'awilt_2.tif'),
            'awilt_3_path': os.path.join(self.workspace_dir, 'awilt_3.tif'),
            'awilt_4_path': os.path.join(self.workspace_dir, 'awilt_4.tif'),
            'awilt_5_path': os.path.join(self.workspace_dir, 'awilt_5.tif'),
            'awilt_6_path': os.path.join(self.workspace_dir, 'awilt_6.tif'),
            'awilt_7_path': os.path.join(self.workspace_dir, 'awilt_7.tif'),
            'awilt_8_path': os.path.join(self.workspace_dir, 'awilt_8.tif'),
            'awilt_9_path': os.path.join(self.workspace_dir, 'awilt_9.tif')
            }

        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')
        som1c_2_path = os.path.join(self.workspace_dir, 'som1c_2.tif')
        som2c_2_path = os.path.join(self.workspace_dir, 'som2c_2.tif')
        som3c_path = os.path.join(self.workspace_dir, 'som3c.tif')
        sand_path = os.path.join(self.workspace_dir, 'sand.tif')
        silt_path = os.path.join(self.workspace_dir, 'silt.tif')
        clay_path = os.path.join(self.workspace_dir, 'clay.tif')
        bulk_d_path = os.path.join(self.workspace_dir, 'bulkd.tif')

        create_random_raster(site_index_path, 1, 1)
        create_random_raster(som1c_2_path, 35., 55.)
        create_random_raster(som2c_2_path, 500., 1500.)
        create_random_raster(som3c_path, 300., 600.)
        create_random_raster(sand_path, 0., 0.5)
        create_random_raster(silt_path, 0., 0.5)
        create_random_raster(bulk_d_path, 0.8, 1.8)
        create_complementary_raster(sand_path, silt_path, clay_path)

        minimum_acceptable_value = 0.01
        maximum_acceptable_value = 0.7
        nodata_value = _TARGET_NODATA

        forage._afiel_awilt(
            site_index_path, site_param_table, som1c_2_path,
            som2c_2_path, som3c_path, sand_path, silt_path, clay_path,
            bulk_d_path, pp_reg)

        for key, path in pp_reg.items():
            self.assert_all_values_in_raster_within_range(
                path, minimum_acceptable_value,
                maximum_acceptable_value, nodata_value)

        for input_raster in [
                site_index_path, som1c_2_path, som2c_2_path, som3c_path,
                sand_path, silt_path, clay_path, bulk_d_path]:
            insert_nodata_values_into_raster(input_raster, _TARGET_NODATA)
            forage._afiel_awilt(
                site_index_path, site_param_table, som1c_2_path,
                som2c_2_path, som3c_path, sand_path, silt_path, clay_path,
                bulk_d_path, pp_reg)
            for key, path in pp_reg.items():
                self.assert_all_values_in_raster_within_range(
                    path, minimum_acceptable_value,
                    maximum_acceptable_value, nodata_value)

        # known inputs
        site_param_table = {1: {'edepth': 0.111}}
        create_random_raster(som1c_2_path, 40, 40)
        create_random_raster(som2c_2_path, 744, 744)
        create_random_raster(som3c_path, 444, 444)
        create_random_raster(sand_path, 0.4, 0.4)
        create_random_raster(silt_path, 0.1, 0.1)
        create_random_raster(bulk_d_path, 0.81, 0.81)
        create_complementary_raster(sand_path, silt_path, clay_path)

        known_afiel_1 = 0.47285
        known_awilt_1 = 0.32424
        known_afiel_4 = 0.47085
        known_awilt_6 = 0.32132
        tolerance = 0.0001

        forage._afiel_awilt(
            site_index_path, site_param_table, som1c_2_path,
            som2c_2_path, som3c_path, sand_path, silt_path, clay_path,
            bulk_d_path, pp_reg)

        self.assert_all_values_in_raster_within_range(
            pp_reg['afiel_1_path'], known_afiel_1 - tolerance,
            known_afiel_1 + tolerance, nodata_value)
        self.assert_all_values_in_raster_within_range(
            pp_reg['awilt_1_path'], known_awilt_1 - tolerance,
            known_awilt_1 + tolerance, nodata_value)
        self.assert_all_values_in_raster_within_range(
            pp_reg['afiel_4_path'], known_afiel_4 - tolerance,
            known_afiel_4 + tolerance, nodata_value)
        self.assert_all_values_in_raster_within_range(
            pp_reg['awilt_6_path'], known_awilt_6 - tolerance,
            known_awilt_6 + tolerance, nodata_value)

    def test_persistent_params(self):
        """Test `persistent_params`.

        Use the function `persistent_params` to calculate wc, eftext, p1co2_2,
        fps1s3, and fps2s3 from randomly generated inputs. Test that each of
        the calculated quantities are within the range [0, 1].  Introduce
        nodata values into the inputs and test that calculated values
        remain inside the specified ranges. Test the function with known inputs
        against values calculated by hand.

        Raises:
            AssertionError if a result from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if a result from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        site_param_table = {
            1: {
                'peftxa': numpy.random.uniform(0.15, 0.35),
                'peftxb': numpy.random.uniform(0.65, 0.85),
                'p1co2a_2': numpy.random.uniform(0.1, 0.2),
                'p1co2b_2': numpy.random.uniform(0.58, 0.78),
                'ps1s3_1': numpy.random.uniform(0.58, 0.78),
                'ps1s3_2': numpy.random.uniform(0.02, 0.04),
                'ps2s3_1': numpy.random.uniform(0.58, 0.78),
                'ps2s3_2': numpy.random.uniform(0.001, 0.005),
                'omlech_1': numpy.random.uniform(0.01, 0.05),
                'omlech_2': numpy.random.uniform(0.06, 0.18),
                'vlossg': 1},
                }

        pp_reg = {
            'afiel_1_path': os.path.join(self.workspace_dir, 'afiel_1.tif'),
            'awilt_1_path': os.path.join(self.workspace_dir, 'awilt.tif'),
            'wc_path': os.path.join(self.workspace_dir, 'wc.tif'),
            'eftext_path': os.path.join(self.workspace_dir, 'eftext.tif'),
            'p1co2_2_path': os.path.join(self.workspace_dir, 'p1co2_2.tif'),
            'fps1s3_path': os.path.join(self.workspace_dir, 'fps1s3.tif'),
            'fps2s3_path': os.path.join(self.workspace_dir, 'fps2s3.tif'),
            'orglch_path': os.path.join(self.workspace_dir, 'orglch.tif'),
            'vlossg_path': os.path.join(self.workspace_dir, 'vlossg.tif'),
        }

        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')
        sand_path = os.path.join(self.workspace_dir, 'sand.tif')
        clay_path = os.path.join(self.workspace_dir, 'clay.tif')

        create_random_raster(site_index_path, 1, 1)
        create_random_raster(sand_path, 0., 0.5)
        create_random_raster(clay_path, 0., 0.5)
        create_random_raster(pp_reg['afiel_1_path'], 0.5, 0.9)
        create_random_raster(pp_reg['awilt_1_path'], 0.01, 0.49)

        acceptable_range_dict = {
            'wc_path': {
                'minimum_acceptable_value': 0.01,
                'maximum_acceptable_value': 0.89,
                'nodata_value': _TARGET_NODATA,
                },
            'eftext_path': {
                'minimum_acceptable_value': 0.15,
                'maximum_acceptable_value': 0.775,
                'nodata_value': _IC_NODATA,
                },
            'p1co2_2_path': {
                'minimum_acceptable_value': 0.1,
                'maximum_acceptable_value': 0.59,
                'nodata_value': _IC_NODATA,
                },
            'fps1s3_path': {
                'minimum_acceptable_value': 0.58,
                'maximum_acceptable_value': 0.8,
                'nodata_value': _IC_NODATA,
                },
            'fps2s3_path': {
                'minimum_acceptable_value': 0.58,
                'maximum_acceptable_value': 0.7825,
                'nodata_value': _IC_NODATA,
                },
            'orglch_path': {
                'minimum_acceptable_value': 0.01,
                'maximum_acceptable_value': 0.14,
                'nodata_value': _IC_NODATA,
                },
            'vlossg_path': {
                'minimum_acceptable_value': 0.009999,
                'maximum_acceptable_value': 0.03001,
                'nodata_value': _IC_NODATA,
                },
        }

        forage._persistent_params(
            site_index_path, site_param_table, sand_path, clay_path, pp_reg)

        for path, ranges in acceptable_range_dict.items():
            self.assert_all_values_in_raster_within_range(
                pp_reg[path], ranges['minimum_acceptable_value'],
                ranges['maximum_acceptable_value'],
                ranges['nodata_value'])

        for input_raster in [
                site_index_path, sand_path, clay_path]:
            insert_nodata_values_into_raster(input_raster, _TARGET_NODATA)
            forage._persistent_params(
                site_index_path, site_param_table, sand_path, clay_path,
                pp_reg)

            for path, ranges in acceptable_range_dict.items():
                self.assert_all_values_in_raster_within_range(
                    pp_reg[path], ranges['minimum_acceptable_value'],
                    ranges['maximum_acceptable_value'],
                    ranges['nodata_value'])

        # known inputs
        site_param_table[1]['peftxa'] = 0.2
        site_param_table[1]['peftxb'] = 0.7
        site_param_table[1]['p1co2a_2'] = 0.18
        site_param_table[1]['p1co2b_2'] = 0.65
        site_param_table[1]['ps1s3_1'] = 0.59
        site_param_table[1]['ps1s3_2'] = 0.03
        site_param_table[1]['ps2s3_1'] = 0.61
        site_param_table[1]['ps2s3_2'] = 0.0022
        site_param_table[1]['omlech_1'] = 0.022
        site_param_table[1]['omlech_2'] = 0.12
        site_param_table[1]['vlossg'] = 1

        create_random_raster(sand_path, 0.22, 0.22)
        create_random_raster(clay_path, 0.22, 0.22)
        create_random_raster(pp_reg['afiel_1_path'], 0.56, 0.56)
        create_random_raster(pp_reg['awilt_1_path'], 0.4, 0.4)

        known_value_dict = {
            'wc_path': {
                'value': 0.16,
                'nodata_value': _TARGET_NODATA,
                },
            'eftext_path': {
                'value': 0.354,
                'nodata_value': _IC_NODATA,
                },
            'p1co2_2_path': {
                'value': 0.323,
                'nodata_value': _IC_NODATA,
                },
            'fps1s3_path': {
                'value': 0.5966,
                'nodata_value': _IC_NODATA,
                },
            'fps2s3_path': {
                'value': 0.61048,
                'nodata_value': _IC_NODATA,
                },
            'orglch_path': {
                'value': 0.0484,
                'nodata_value': _IC_NODATA,
                },
            'vlossg_path': {
                'value': 0.018,
                'nodata_value': _IC_NODATA,
            }
        }
        tolerance = 0.0001

        forage._persistent_params(
            site_index_path, site_param_table, sand_path, clay_path,
            pp_reg)

        for path, values in known_value_dict.items():
            self.assert_all_values_in_raster_within_range(
                pp_reg[path], values['value'] - tolerance,
                values['value'] + tolerance, values['nodata_value'])

    def test_aboveground_ratio(self):
        """Test `_aboveground_ratio`.

        Use the function `_aboveground_ratio` to calculate the C/N or P
        ratio of decomposing aboveground material from random inputs. Test
        that the calculated ratio, agdrat, is within the range [1, 150].
        Introduce nodata values into the inputs and test that calculated
        agdrat remains inside the range [1, 150]. Calculate aboveground
        ratio from known inputs and compare to result calculated by hand.

        Raises:
            AssertionError if agdrat from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if agdrat from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        array_shape = (10, 10)
        tolerance = 0.0001

        tca = numpy.random.uniform(300, 700, array_shape)
        anps = numpy.random.uniform(1, numpy.amin(tca), array_shape)
        pcemic_1 = numpy.random.uniform(12, 20, array_shape)
        pcemic_2 = numpy.random.uniform(3, 11, array_shape)
        pcemic_3 = numpy.random.uniform(0.001, 0.1, array_shape)

        minimum_acceptable_agdrat = 2.285
        maximum_acceptable_agdrat = numpy.amax(pcemic_1)
        agdrat_nodata = _TARGET_NODATA

        agdrat = forage._aboveground_ratio(
            anps, tca, pcemic_1, pcemic_2, pcemic_3)

        self.assert_all_values_in_array_within_range(
            agdrat, minimum_acceptable_agdrat, maximum_acceptable_agdrat,
            agdrat_nodata)

        for input_array in [anps, tca]:
            insert_nodata_values_into_array(input_array, _TARGET_NODATA)
            agdrat = forage._aboveground_ratio(
                anps, tca, pcemic_1, pcemic_2, pcemic_3)

            self.assert_all_values_in_array_within_range(
                agdrat, minimum_acceptable_agdrat, maximum_acceptable_agdrat,
                agdrat_nodata)
        for input_array in [pcemic_1, pcemic_2, pcemic_3]:
            insert_nodata_values_into_array(input_array, _IC_NODATA)
            agdrat = forage._aboveground_ratio(
                anps, tca, pcemic_1, pcemic_2, pcemic_3)

            self.assert_all_values_in_array_within_range(
                agdrat, minimum_acceptable_agdrat, maximum_acceptable_agdrat,
                agdrat_nodata)

        # known inputs: econt > pcemic_3
        tca = 413
        anps = 229
        pcemic_1 = 17.4
        pcemic_2 = 3.2
        pcemic_3 = 0.04

        known_agdrat = 3.2
        point_agdrat = agdrat_point(anps, tca, pcemic_1, pcemic_2, pcemic_3)
        self.assertAlmostEqual(known_agdrat, point_agdrat)

        tca_ar = numpy.full(array_shape, tca)
        anps_ar = numpy.full(array_shape, anps)
        pcemic_1_ar = numpy.full(array_shape, pcemic_1)
        pcemic_2_ar = numpy.full(array_shape, pcemic_2)
        pcemic_3_ar = numpy.full(array_shape, pcemic_3)

        agdrat = forage._aboveground_ratio(
            anps_ar, tca_ar, pcemic_1_ar, pcemic_2_ar, pcemic_3_ar)
        self.assert_all_values_in_array_within_range(
            agdrat, point_agdrat - tolerance, point_agdrat + tolerance,
            agdrat_nodata)

        # known inputs: econt < pcemic_3
        tca = 413.
        anps = 100.
        pcemic_1 = 17.4
        pcemic_2 = 3.2
        pcemic_3 = 0.11
        point_agdrat = agdrat_point(anps, tca, pcemic_1, pcemic_2, pcemic_3)

        tca_ar = numpy.full(array_shape, tca)
        anps_ar = numpy.full(array_shape, anps)
        pcemic_1_ar = numpy.full(array_shape, pcemic_1)
        pcemic_2_ar = numpy.full(array_shape, pcemic_2)
        pcemic_3_ar = numpy.full(array_shape, pcemic_3)

        agdrat = forage._aboveground_ratio(
            anps_ar, tca_ar, pcemic_1_ar, pcemic_2_ar, pcemic_3_ar)
        self.assert_all_values_in_array_within_range(
            agdrat, point_agdrat - tolerance, point_agdrat + tolerance,
            agdrat_nodata)

    def test_structural_ratios(self):
        """Test `_structural_ratios`.

        Use the function `_structural_ratios` to calculate rnewas_1_1,
        rnewas_1_2, rnewas_2_1, rnewas_2_2, rnewbs_1_2, and rnewbs_2_2 from
        randomly generated inputs. Test that each of the calculated quantities
        are within the range [1, 1500].  Introduce nodata values into the
        inputs and test that calculated values remain inside the specified
        ranges.

        Raises:
            AssertionError if rnewas_1_1 is outside the range [1, 1500]
            AssertionError if rnewas_1_2 is outside the range [1, 1500]
            AssertionError if rnewas_2_1 is outside the range [1, 1500]
            AssertionError if rnewas_2_2 is outside the range [1, 1500]
            AssertionError if rnewbs_1_1 is outside the range [1, 1500]
            AssertionError if rnewbs_2_2 is outside the range [1, 1500]
            AssertionError if rnewbs_2_1 is outside the range [1, 1500]
            AssertionError if rnewbs_2_2 is outside the range [1, 1500]

        Returns:
            None

        """
        from rangeland_production import forage

        site_param_table = {
            1: {
                'pcemic1_2_1': numpy.random.uniform(5, 12),
                'pcemic1_1_1': numpy.random.uniform(13, 23),
                'pcemic1_3_1': numpy.random.uniform(0.01, 0.05),
                'pcemic2_2_1': numpy.random.uniform(5, 12),
                'pcemic2_1_1': numpy.random.uniform(13, 23),
                'pcemic2_3_1': numpy.random.uniform(0.01, 0.05),
                'rad1p_1_1': numpy.random.uniform(8, 16),
                'rad1p_2_1': numpy.random.uniform(2, 5),
                'rad1p_3_1': numpy.random.uniform(2, 5),
                'varat1_1_1': numpy.random.uniform(12, 16),
                'varat22_1_1': numpy.random.uniform(15, 25),

                'pcemic1_2_2': numpy.random.uniform(90, 110),
                'pcemic1_1_2': numpy.random.uniform(170, 230),
                'pcemic1_3_2': numpy.random.uniform(0.0005, 0.0025),
                'pcemic2_2_2': numpy.random.uniform(75, 125),
                'pcemic2_1_2': numpy.random.uniform(200, 300),
                'pcemic2_3_2': numpy.random.uniform(0.0005, 0.0025),
                'rad1p_1_2': numpy.random.uniform(200, 300),
                'rad1p_2_2': numpy.random.uniform(3, 7),
                'rad1p_3_2': numpy.random.uniform(50, 150),
                'varat1_1_2': numpy.random.uniform(125, 175),
                'varat22_1_2': numpy.random.uniform(350, 450)},
                }

        sv_reg = {
            'strucc_1_path': os.path.join(self.workspace_dir, 'strucc_1.tif'),
            'struce_1_1_path': os.path.join(
                self.workspace_dir, 'struce_1_1.tif'),
            'struce_1_2_path': os.path.join(
                self.workspace_dir, 'struce_1_2.tif'),

        }
        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')
        create_random_raster(site_index_path, 1, 1)
        create_random_raster(sv_reg['strucc_1_path'], 120, 1800)
        create_random_raster(sv_reg['struce_1_1_path'], 0.5, 10)
        create_random_raster(sv_reg['struce_1_2_path'], 0.1, 0.50)

        pp_reg = {
            'rnewas_1_1_path': os.path.join(
                self.workspace_dir, 'rnewas_1_1.tif'),
            'rnewas_1_2_path': os.path.join(
                self.workspace_dir, 'rnewas_1_2.tif'),
            'rnewas_2_1_path': os.path.join(
                self.workspace_dir, 'rnewas_2_1.tif'),
            'rnewas_2_2_path': os.path.join(
                self.workspace_dir, 'rnewas_2_2.tif'),
            'rnewbs_1_1_path': os.path.join(
                self.workspace_dir, 'rnewbs_1_1.tif'),
            'rnewbs_1_2_path': os.path.join(
                self.workspace_dir, 'rnewbs_1_2.tif'),
            'rnewbs_2_1_path': os.path.join(
                self.workspace_dir, 'rnewbs_2_1.tif'),
            'rnewbs_2_2_path': os.path.join(
                self.workspace_dir, 'rnewbs_2_2.tif'),
        }

        minimum_acceptable_value = 1
        maximum_acceptable_value = 1500
        nodata_value = _TARGET_NODATA

        forage._structural_ratios(
            site_index_path, site_param_table, sv_reg, pp_reg)

        for key, path in pp_reg.items():
            self.assert_all_values_in_raster_within_range(
                path, minimum_acceptable_value,
                maximum_acceptable_value, nodata_value)

        for input_raster in [
                site_index_path, sv_reg['strucc_1_path'],
                sv_reg['struce_1_1_path'], sv_reg['struce_1_2_path']]:
            insert_nodata_values_into_raster(input_raster, _TARGET_NODATA)
            forage._structural_ratios(
                site_index_path, site_param_table, sv_reg, pp_reg)

            for key, path in pp_reg.items():
                self.assert_all_values_in_raster_within_range(
                    path, minimum_acceptable_value,
                    maximum_acceptable_value, nodata_value)

    def test_yearly_tasks(self):
        """Test `_yearly_tasks`.

        Use `_yearly_tasks` to calculate annual precipitation, annual
        atmospheric N deposition, and the fraction of residue which is lignin
        from random inputs. Test that the function fails if fewer than 12
        months of precipitation are supplied. Test that the function fails if
        the dates of precipitation inputs do not fill the 12 months surrounding
        the current month. Test that annual precipitation falls inside the
        range [0, 72]. Test that annual atmospheric N deposition falls inside
        the range [0, 37]. Introduce nodata values into input rasters and test
        that atmospheric N deposition remains within the specified range.

        Raises:
            AssertionError if `_yearly_tasks` does not fail with fewer than 12
                months of precipitation rasters supplied
            AssertionError if `_yearly_tasks` does not fail with precipitation
                rasters supplied not within 12 months of current month
            AssertionError if a result from random inputs is outside the
                known possible range given the range of inputs

        Returns:
            None

        """
        from rangeland_production import forage

        month_index = numpy.random.randint(0, 100)
        site_param_table = {
            1: {
                'epnfa_1': numpy.random.uniform(0, 1),
                'epnfa_2': numpy.random.uniform(0, 0.5),

                }
            }
        veg_trait_table = {
            1: {
                'fligni_1_1': 0.02,
                'fligni_2_1': 0.0012,
                'fligni_1_2': 0.26,
                'fligni_2_2': -0.0015,
            }
        }
        pft_id_set = [1]
        complete_aligned_inputs = {
            'precip_{}'.format(month): os.path.join(
                self.workspace_dir, 'precip_{}.tif'.format(month)) for
            month in range(month_index, month_index + 12)
        }
        complete_aligned_inputs['site_index'] = os.path.join(
            self.workspace_dir, 'site_index.tif')

        year_reg = {
            'annual_precip_path': os.path.join(
                self.workspace_dir, 'annual_precip.tif'),
            'baseNdep_path': os.path.join(self.workspace_dir, 'baseNdep.tif'),
            'pltlig_above_1': os.path.join(
                self.workspace_dir, 'pltlig_above.tif'),
            'pltlig_below_1': os.path.join(
                self.workspace_dir, 'pltlig_below.tif'),
        }

        create_random_raster(complete_aligned_inputs['site_index'], 1, 1)
        precip_keys = [
            'precip_{}'.format(month) for month in
            range(month_index, month_index + 12)]
        for key in precip_keys:
            create_random_raster(complete_aligned_inputs[key], 0, 6)

        # fewer than 12 months of precip rasters
        modified_inputs = complete_aligned_inputs.copy()
        removed_key = modified_inputs.pop('precip_{}'.format(
            numpy.random.randint(month_index, month_index + 12)))
        with self.assertRaises(ValueError):
            forage._yearly_tasks(
                modified_inputs, site_param_table, veg_trait_table,
                month_index, pft_id_set, year_reg)

        # 12 months of precip rasters supplied, but outside 12 month window of
        # current month
        modified_inputs['precip_{}'.format(month_index + 13)] = os.path.join(
            'precip_{}.tif'.format(month_index + 13))
        with self.assertRaises(ValueError):
            forage._yearly_tasks(
                modified_inputs, site_param_table, veg_trait_table,
                month_index, pft_id_set, year_reg)

        # complete intact inputs
        minimum_acceptable_annual_precip = 0
        maximum_acceptabe_annual_precip = 72
        precip_nodata = _TARGET_NODATA

        minimum_acceptable_Ndep = 0
        maximum_acceptable_Ndep = 37
        Ndep_nodata = _TARGET_NODATA

        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['annual_precip_path'], minimum_acceptable_annual_precip,
            maximum_acceptabe_annual_precip, precip_nodata)
        self.assert_all_values_in_raster_within_range(
            year_reg['baseNdep_path'], minimum_acceptable_Ndep,
            maximum_acceptable_Ndep, Ndep_nodata)

        for key, input_raster in complete_aligned_inputs.items():
            insert_nodata_values_into_raster(input_raster, _TARGET_NODATA)
            forage._yearly_tasks(
                complete_aligned_inputs, site_param_table, veg_trait_table,
                month_index, pft_id_set, year_reg)
            self.assert_all_values_in_raster_within_range(
                year_reg['annual_precip_path'],
                minimum_acceptable_annual_precip,
                maximum_acceptabe_annual_precip, precip_nodata)
            self.assert_all_values_in_raster_within_range(
                year_reg['baseNdep_path'], minimum_acceptable_Ndep,
                maximum_acceptable_Ndep, Ndep_nodata)

        # known inputs, fraction of plant residue that is lignin
        tolerance = 0.0000001
        for key in precip_keys:
            create_constant_raster(
                complete_aligned_inputs[key], 0, n_rows=3, n_cols=3)
        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_above_1'], 0.02 - tolerance, 0.02 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_below_1'], 0.26 - tolerance, 0.26 + tolerance,
            _TARGET_NODATA)

        for key in precip_keys:
            create_constant_raster(
                complete_aligned_inputs[key], 6, n_rows=3, n_cols=3)
        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_above_1'], 0.106 - tolerance, 0.1064 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_below_1'], 0.152 - tolerance, 0.152 + tolerance,
            _TARGET_NODATA)
        for key, input_raster in complete_aligned_inputs.items():
            insert_nodata_values_into_raster(input_raster, _TARGET_NODATA)
        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_above_1'], 0.1064 - tolerance, 0.1064 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_below_1'], 0.152 - tolerance, 0.152 + tolerance,
            _TARGET_NODATA)

        for key in precip_keys:
            create_constant_raster(
                complete_aligned_inputs[key], 40, n_rows=3, n_cols=3)
        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_above_1'], 0.5 - tolerance, 0.5 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_below_1'], 0.02 - tolerance, 0.02 + tolerance,
            _TARGET_NODATA)

        for key in precip_keys:
            create_constant_raster(
                complete_aligned_inputs[key], 0.03, n_rows=3, n_cols=3)
        forage._yearly_tasks(
            complete_aligned_inputs, site_param_table, veg_trait_table,
            month_index, pft_id_set, year_reg)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_above_1'], 0.020432 - tolerance,
            0.020432 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            year_reg['pltlig_below_1'], 0.25946 - tolerance,
            0.25946 + tolerance, _TARGET_NODATA)

    def test_reference_evapotranspiration(self):
        """Test `_reference_evapotranspiration`.

        Use the function `_reference_evapotranspiration` to calculate reference
        evapotranspiration (ET) from random inputs. Test that the calculated
        reference ET is within the range [0, 32]. Introduce nodata values into
        the inputs and test that the result remains inside the range [0, 31].
        Test the function with known inputs against a value calculated by hand.

        Raises:
            AssertionError if evapotranspiration from random inputs is outside
                the known possible range given the range of inputs
            AssertionError if evapotranspiration from known inputs is outside
                the range [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        max_temp_path = os.path.join(self.workspace_dir, 'max_temp.tif')
        min_temp_path = os.path.join(self.workspace_dir, 'min_temp.tif')
        shwave_path = os.path.join(self.workspace_dir, 'shwave.tif')
        fwloss_4_path = os.path.join(self.workspace_dir, 'fwloss_4.tif')

        create_random_raster(max_temp_path, 21, 40)
        create_random_raster(min_temp_path, -20, 20)
        create_random_raster(shwave_path, 0, 1125)
        create_random_raster(fwloss_4_path, 0, 1)

        pevap_path = os.path.join(self.workspace_dir, 'pevap.tif')

        minimum_acceptable_ET = 0
        maximum_acceptable_ET = 32
        ET_nodata = _TARGET_NODATA

        forage._reference_evapotranspiration(
            max_temp_path, min_temp_path, shwave_path, fwloss_4_path,
            pevap_path)

        self.assert_all_values_in_raster_within_range(
            pevap_path, minimum_acceptable_ET, maximum_acceptable_ET,
            ET_nodata)

        insert_nodata_values_into_raster(max_temp_path, _IC_NODATA)
        insert_nodata_values_into_raster(min_temp_path, _IC_NODATA)
        insert_nodata_values_into_raster(shwave_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(fwloss_4_path, _IC_NODATA)

        forage._reference_evapotranspiration(
            max_temp_path, min_temp_path, shwave_path, fwloss_4_path,
            pevap_path)

        self.assert_all_values_in_raster_within_range(
            pevap_path, minimum_acceptable_ET, maximum_acceptable_ET,
            ET_nodata)

        # known inputs
        create_random_raster(max_temp_path, 23, 23)
        create_random_raster(min_temp_path, -2, -2)
        create_random_raster(shwave_path, 880, 880)
        create_random_raster(fwloss_4_path, 0.6, 0.6)

        known_ET = 9.5465
        tolerance = 0.0001

        forage._reference_evapotranspiration(
            max_temp_path, min_temp_path, shwave_path, fwloss_4_path,
            pevap_path)

        self.assert_all_values_in_raster_within_range(
            pevap_path, known_ET - tolerance, known_ET + tolerance,
            ET_nodata)

    def test_potential_production(self):
        """Test `_potential_production`.

        Use the function `_potential_production` to calculate h2ogef_1 and
        total potential production from random inputs. Test that h2ogef_1, the
        limiting factor of water availability on growth, is inside the range
        [0.009, 1]. Test that total production is inside the range [0, 675].
        Introduce nodata values into inputs and test that h2ogef_1 and
        potential production remain inside the specified ranges.

        Raises:
            AssertionError if h2ogef_1 is outside the range [0.009, 1]
            AssertionError if total potential production is outside the range
                [0, 675]

        Returns:
            None

        """
        from rangeland_production import forage

        month_index = 10
        current_month = 6
        pft_id_set = set([1, 2])

        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site_index.tif'),
            'max_temp_{}'.format(current_month): os.path.join(
                self.workspace_dir, 'max_temp.tif'),
            'min_temp_{}'.format(current_month): os.path.join(
                self.workspace_dir, 'min_temp.tif'),
            'precip_{}'.format(month_index): os.path.join(
                self.workspace_dir, 'precip.tif'),
        }
        create_random_raster(aligned_inputs['site_index'], 1, 1)
        create_random_raster(
            aligned_inputs['max_temp_{}'.format(current_month)], 10, 30)
        create_random_raster(
            aligned_inputs['min_temp_{}'.format(current_month)], -10, 9)
        create_random_raster(
            aligned_inputs['precip_{}'.format(month_index)], 0, 6)

        for pft_i in pft_id_set:
            aligned_inputs['pft_{}'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'pft_{}.tif'.format(pft_i))
            create_random_raster(
                aligned_inputs['pft_{}'.format(pft_i)], 0, 1)

        site_param_table = {
            1: {
                'pmxbio': numpy.random.uniform(500, 700),
                'pmxtmp': numpy.random.uniform(-0.0025, 0),
                'pmntmp': numpy.random.uniform(0, 0.01),
                'fwloss_4': numpy.random.uniform(0, 1),
                'pprpts_1': numpy.random.uniform(0, 1),
                'pprpts_2': numpy.random.uniform(0.5, 1.5),
                'pprpts_3': numpy.random.uniform(0, 1),
            }
        }
        veg_trait_table = {}
        for pft_i in pft_id_set:
            veg_trait_table[pft_i] = {
                'ppdf_1': numpy.random.uniform(10, 30),
                'ppdf_2': numpy.random.uniform(31, 50),
                'ppdf_3': numpy.random.uniform(0, 1),
                'ppdf_4': numpy.random.uniform(0, 10),
                'biok5': numpy.random.uniform(0, 2000),
                'prdx_1': numpy.random.uniform(0.1, 0.6),
                'growth_months': ['3', '4', '5', '6'],
            }

        sv_reg = {
            'strucc_1_path': os.path.join(self.workspace_dir, 'strucc_1.tif'),
        }
        create_random_raster(sv_reg['strucc_1_path'], 0, 200)
        for pft_i in pft_id_set:
            sv_reg['aglivc_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'aglivc_{}.tif'.format(pft_i))
            create_random_raster(sv_reg['aglivc_{}_path'.format(pft_i)], 0, 50)
            sv_reg['stdedc_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'stdedc_{}.tif'.format(pft_i))
            create_random_raster(sv_reg['stdedc_{}_path'.format(pft_i)], 0, 50)
            sv_reg['avh2o_1_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'avh2o_1_{}.tif'.format(pft_i))
            create_random_raster(
                sv_reg['avh2o_1_{}_path'.format(pft_i)], 0, 3.5)

        pp_reg = {
            'wc_path': os.path.join(self.workspace_dir, 'wc.tif')
        }
        create_random_raster(pp_reg['wc_path'], 0.01, 0.9)

        month_reg = {}
        for pft_i in pft_id_set:
            month_reg['h2ogef_1_{}'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'h2ogef_1_{}.tif'.format(pft_i))
            month_reg['tgprod_pot_prod_{}'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'tgprod_pot_prod_{}.tif'.format(pft_i))

        minimum_acceptable_h2ogef_1 = 0.009
        maximum_acceptable_h2ogef_1 = 1

        minimum_acceptable_potential_production = 0
        maximum_acceptable_potential_production = 675

        forage._potential_production(
            aligned_inputs, site_param_table, current_month, month_index,
            pft_id_set, veg_trait_table, sv_reg, pp_reg, month_reg)

        for pft_i in pft_id_set:
            self.assert_all_values_in_raster_within_range(
                month_reg['h2ogef_1_{}'.format(pft_i)],
                minimum_acceptable_h2ogef_1,
                maximum_acceptable_h2ogef_1, _TARGET_NODATA)
            self.assert_all_values_in_raster_within_range(
                month_reg['tgprod_pot_prod_{}'.format(pft_i)],
                minimum_acceptable_potential_production,
                maximum_acceptable_potential_production, _TARGET_NODATA)

        insert_nodata_values_into_raster(
            aligned_inputs['site_index'], _TARGET_NODATA)
        insert_nodata_values_into_raster(
            aligned_inputs['max_temp_{}'.format(current_month)],
            -9999)
        insert_nodata_values_into_raster(
            aligned_inputs['min_temp_{}'.format(current_month)],
            _IC_NODATA)
        insert_nodata_values_into_raster(
            aligned_inputs['pft_{}'.format(list(pft_id_set)[0])],
            _TARGET_NODATA)
        insert_nodata_values_into_raster(
            sv_reg['aglivc_{}_path'.format(list(pft_id_set)[0])], _SV_NODATA)
        insert_nodata_values_into_raster(
            sv_reg['avh2o_1_{}_path'.format(list(pft_id_set)[1])],
            _TARGET_NODATA)
        insert_nodata_values_into_raster(pp_reg['wc_path'], _TARGET_NODATA)

        forage._potential_production(
            aligned_inputs, site_param_table, current_month, month_index,
            pft_id_set, veg_trait_table, sv_reg, pp_reg, month_reg)

        for pft_i in pft_id_set:
            self.assert_all_values_in_raster_within_range(
                month_reg['h2ogef_1_{}'.format(pft_i)],
                minimum_acceptable_h2ogef_1,
                maximum_acceptable_h2ogef_1, _TARGET_NODATA)
            self.assert_all_values_in_raster_within_range(
                month_reg['tgprod_pot_prod_{}'.format(pft_i)],
                minimum_acceptable_potential_production,
                maximum_acceptable_potential_production, _TARGET_NODATA)

        # average temperature < 0, no potential for growth
        create_constant_raster(
            aligned_inputs['max_temp_{}'.format(current_month)], 2.,
            n_cols=NCOLS, n_rows=NROWS)
        create_constant_raster(
            aligned_inputs['min_temp_{}'.format(current_month)], -10.,
            n_cols=NCOLS, n_rows=NROWS)
        minimum_acceptable_potential_production = 0
        maximum_acceptable_potential_production = 0

        forage._potential_production(
            aligned_inputs, site_param_table, current_month, month_index,
            pft_id_set, veg_trait_table, sv_reg, pp_reg, month_reg)

        for pft_i in pft_id_set:
            self.assert_all_values_in_raster_within_range(
                month_reg['tgprod_pot_prod_{}'.format(pft_i)],
                minimum_acceptable_potential_production,
                maximum_acceptable_potential_production, _TARGET_NODATA)

    def test_calc_favail_P(self):
        """Test `_calc_favail_P`.

        Use the function `_calc_favail_P` to calculate the intermediate
        parameter favail_P from random inputs.  Test that favail_P is
        inside the range [0, 1]. Introduce nodata values into inputs and test
        that favail_P remains inside the range [0, 1]. Test the function with
        known inputs against values calculated by hand.

        Raises:
            AssertionError if favail_P from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if favail_ from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        sv_reg = {
            'minerl_1_1_path': os.path.join(
                self.workspace_dir, 'minerl_1_1.tif')
        }
        param_val_dict = {
            'favail_4': os.path.join(self.workspace_dir, 'favail_4.tif'),
            'favail_5': os.path.join(self.workspace_dir, 'favail_5.tif'),
            'favail_6': os.path.join(self.workspace_dir, 'favail_6.tif'),
            'favail_2': os.path.join(self.workspace_dir, 'favail_2.tif'),
        }

        create_random_raster(sv_reg['minerl_1_1_path'], 3, 8)
        create_random_raster(param_val_dict['favail_4'], 0, 1)
        create_random_raster(param_val_dict['favail_5'], 0, 1)
        create_random_raster(param_val_dict['favail_6'], 1, 3)

        forage._calc_favail_P(sv_reg, param_val_dict)

        minimum_acceptable_favail_P = 0
        maximum_acceptable_favail_P = 1

        self.assert_all_values_in_raster_within_range(
            param_val_dict['favail_2'],
            minimum_acceptable_favail_P,
            maximum_acceptable_favail_P, _IC_NODATA)

        insert_nodata_values_into_raster(sv_reg['minerl_1_1_path'], _SV_NODATA)
        for input_raster in [
                param_val_dict['favail_4'], param_val_dict['favail_5'],
                param_val_dict['favail_6']]:
            insert_nodata_values_into_raster(input_raster, _IC_NODATA)
            forage._calc_favail_P(sv_reg, param_val_dict)
            self.assert_all_values_in_raster_within_range(
                param_val_dict['favail_2'],
                minimum_acceptable_favail_P,
                maximum_acceptable_favail_P, _IC_NODATA)

        # known inputs
        create_random_raster(sv_reg['minerl_1_1_path'], 4.5, 4.5)
        create_random_raster(param_val_dict['favail_4'], 0.2, 0.2)
        create_random_raster(param_val_dict['favail_5'], 0.5, 0.5)
        create_random_raster(param_val_dict['favail_6'], 2.3, 2.3)

        known_favail_2 = 0.5
        tolerance = 0.0001

        forage._calc_favail_P(sv_reg, param_val_dict)
        self.assert_all_values_in_raster_within_range(
            param_val_dict['favail_2'],
            known_favail_2 - tolerance, known_favail_2 + tolerance,
            _IC_NODATA)

    def test_raster_list_sum(self):
        """Test `raster_list_sum`.

        Use the function `raster_list_sum` to calculate the sum across pixels
        in three rasters containing nodata.  Test that when
        nodata_remove=False, the result also contains nodata values. Test
        that when nodata_remove=True, nodata pixels are treated as zero.

        Raises:
            AssertionError if result raster does not contain nodata values
                in same position as input rasters

        Returns:
            None

        """
        from rangeland_production import forage

        num_rasters = numpy.random.randint(1, 10)
        raster_list = [
            os.path.join(self.workspace_dir, '{}.tif'.format(r)) for r in
            range(num_rasters)]

        for input_raster in raster_list:
            create_random_raster(input_raster, 1, 1)

        input_nodata = -999
        target_path = os.path.join(self.workspace_dir, 'result.tif')
        target_nodata = -9.99

        # input rasters include no nodata values
        forage.raster_list_sum(
            raster_list, input_nodata, target_path, target_nodata,
            nodata_remove=False)
        self.assert_all_values_in_raster_within_range(
            target_path, num_rasters, num_rasters, target_nodata)

        forage.raster_list_sum(
            raster_list, input_nodata, target_path, target_nodata,
            nodata_remove=True)
        self.assert_all_values_in_raster_within_range(
            target_path, num_rasters, num_rasters, target_nodata)

        # one input raster includes nodata values
        insert_nodata_values_into_raster(raster_list[0], input_nodata)

        forage.raster_list_sum(
            raster_list, input_nodata, target_path, target_nodata,
            nodata_remove=False)
        self.assert_all_values_in_raster_within_range(
            target_path, num_rasters, num_rasters, target_nodata)

        # assert that raster_list[0] and target_path include nodata
        # values in same locations
        input_including_nodata = gdal.OpenEx(raster_list[0])
        result_including_nodata = gdal.OpenEx(target_path)
        input_band = input_including_nodata.GetRasterBand(1)
        result_band = result_including_nodata.GetRasterBand(1)
        input_array = input_band.ReadAsArray()
        result_array = result_band.ReadAsArray()

        sum_input_mask = numpy.sum(input_array[input_array == input_nodata])
        sum_result_mask = numpy.sum(input_array[result_array == target_nodata])

        self.assertEqual(
            sum_input_mask, sum_result_mask,
            msg="Result raster must contain nodata values in same " +
            "position as input")

        input_band = None
        result_band = None
        input_including_nodata = None
        result_including_nodata = None

        forage.raster_list_sum(
            raster_list, input_nodata, target_path, target_nodata,
            nodata_remove=True)

        # assert that minimum value in target_path is num_rasters - 1
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (target_path, 1)):
            if len(raster_block[raster_block != target_nodata]) == 0:
                continue
            min_val = numpy.amin(
                raster_block[raster_block != target_nodata])
            self.assertGreaterEqual(
                min_val, (num_rasters - 1),
                msg="Raster appears to contain nodata values")

    def test_weighted_state_variable_sum(self):
        """Test `weighted_state_variable_sum`.

        Use the function `weighted_state_variable_sum` to calculate the
        weighted sum of a state variable across plant functional types. Test
        that the calculated sum matches values calculated by hand.

        Raises:
            AssertionError if the result calculated by
                `weighted_state_variable_sum` is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        sv = 'state_variable'
        pft_id_set = [2, 5, 7]
        percent_cover_dict = {
            pft_id_set[0]: 0.3,
            pft_id_set[1]: 0.001,
            pft_id_set[2]: 0.58,
        }
        sv_value_dict = {
            pft_id_set[0]: 20.,
            pft_id_set[1]: 300.84,
            pft_id_set[2]: 102.,
        }
        sv_reg = {}
        aligned_inputs = {}
        for pft_i in pft_id_set:
            aligned_inputs['pft_{}'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'pft_{}.tif'.format(pft_i))
            create_constant_raster(
                aligned_inputs['pft_{}'.format(pft_i)],
                percent_cover_dict[pft_i])
            sv_reg['{}_{}_path'.format(sv, pft_i)] = os.path.join(
                self.workspace_dir, '{}_{}.tif'.format(sv, pft_i))
            create_constant_raster(
                sv_reg['{}_{}_path'.format(sv, pft_i)],
                sv_value_dict[pft_i])
        weighted_sum_path = os.path.join(
            self.workspace_dir, 'weighted_sum.tif')

        tolerance = 0.0001

        # known inputs
        known_weighted_sum = 65.46084
        forage.weighted_state_variable_sum(
            sv, sv_reg, aligned_inputs, pft_id_set, weighted_sum_path)
        self.assert_all_values_in_raster_within_range(
            weighted_sum_path, known_weighted_sum - tolerance,
            known_weighted_sum + tolerance, _TARGET_NODATA)

        # one pft has zero percent cover
        percent_cover_dict[pft_id_set[0]] = 0.
        create_constant_raster(
            aligned_inputs['pft_{}'.format(pft_id_set[0])],
            percent_cover_dict[pft_id_set[0]])

        known_weighted_sum = 59.46084
        forage.weighted_state_variable_sum(
            sv, sv_reg, aligned_inputs, pft_id_set, weighted_sum_path)
        self.assert_all_values_in_raster_within_range(
            weighted_sum_path, known_weighted_sum - tolerance,
            known_weighted_sum + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_raster(
            aligned_inputs['pft_{}'.format(pft_id_set[0])], _TARGET_NODATA)
        insert_nodata_values_into_raster(
            sv_reg['{}_{}_path'.format(sv, pft_id_set[2])], _SV_NODATA)

        forage.weighted_state_variable_sum(
            sv, sv_reg, aligned_inputs, pft_id_set, weighted_sum_path)

    def test_calc_available_nutrient(self):
        """Test `_calc_available_nutrient`.

        Use the function `_calc_available_nutrient` to calculate available
        nutrient from random results. Test that the calculated nutrient
        available is inside the range [0, 323]. Introduce nodata values into
        inputs and test that available nutrient remains inside the range
        [0, 323]. Test the function with known values against values calculated
        by hand.

        Raises:
            AssertionError if a result from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if a result from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        pft_i = numpy.random.randint(0, 4)
        pft_param_dict = {
            'snfxmx_1': numpy.random.uniform(0, 1),
            'nlaypg': numpy.random.randint(1, 10),
        }
        sv_reg = {
            'bglivc_{}_path'.format(pft_i): os.path.join(
                self.workspace_dir, 'bglivc_path.tif'),
            'crpstg_1_{}_path'.format(pft_i): os.path.join(
                self.workspace_dir, 'crpstg_1_{}.tif'.format(pft_i)),
            'crpstg_2_{}_path'.format(pft_i): os.path.join(
                self.workspace_dir, 'crpstg_2_{}.tif'.format(pft_i)),
        }

        site_param_table = {
            1: {
                'rictrl': numpy.random.uniform(0.005, 0.02),
                'riint': numpy.random.uniform(0.6, 1),
                }
            }
        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')
        favail_path = os.path.join(self.workspace_dir, 'favail.tif')
        tgprod_path = os.path.join(self.workspace_dir, 'tgprod.tif')
        availm_path = os.path.join(self.workspace_dir, 'availm.tif')

        create_random_raster(site_index_path, 1, 1)
        create_random_raster(sv_reg['bglivc_{}_path'.format(pft_i)], 90, 180)
        create_random_raster(sv_reg['crpstg_1_{}_path'.format(pft_i)], 0, 3)
        create_random_raster(sv_reg['crpstg_2_{}_path'.format(pft_i)], 0, 1)
        create_random_raster(favail_path, 0, 1)
        create_random_raster(tgprod_path, 0, 675)
        create_random_raster(availm_path, 0, 55)

        eavail_path = os.path.join(self.workspace_dir, 'eavail.tif')

        minimum_acceptable_eavail = 0
        maximum_acceptable_evail = 323

        for iel in [1, 2]:
            forage._calc_available_nutrient(
                pft_i, iel, pft_param_dict, sv_reg, site_param_table,
                site_index_path, availm_path, favail_path, tgprod_path,
                eavail_path)

            self.assert_all_values_in_raster_within_range(
                eavail_path, minimum_acceptable_eavail,
                maximum_acceptable_evail, _TARGET_NODATA)

        insert_nodata_values_into_raster(site_index_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(
            sv_reg['bglivc_{}_path'.format(pft_i)], _TARGET_NODATA)
        insert_nodata_values_into_raster(tgprod_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(availm_path, _TARGET_NODATA)

        for iel in [1, 2]:
            forage._calc_available_nutrient(
                pft_i, iel, pft_param_dict, sv_reg, site_param_table,
                site_index_path, availm_path, favail_path, tgprod_path,
                eavail_path)

            self.assert_all_values_in_raster_within_range(
                eavail_path, minimum_acceptable_eavail,
                maximum_acceptable_evail, _TARGET_NODATA)

        # known inputs
        create_random_raster(sv_reg['bglivc_{}_path'.format(pft_i)], 100, 100)
        create_random_raster(
            sv_reg['crpstg_1_{}_path'.format(pft_i)], 0.8, 0.8)
        create_random_raster(
            sv_reg['crpstg_2_{}_path'.format(pft_i)], 0.8, 0.8)
        create_random_raster(favail_path, 0.3, 0.3)
        create_random_raster(tgprod_path, 300, 300)
        create_random_raster(availm_path, 4, 4)

        pft_param_dict['snfxmx_1'] = 0.4
        pft_param_dict['nlaypg'] = 4

        site_param_table[1]['rictrl'] = 0.013
        site_param_table[1]['riint'] = 0.65

        known_N_avail = 49.9697
        known_P_avail = 1.9697
        tolerance = 0.0001

        iel = 1
        eavail_path = os.path.join(self.workspace_dir, 'eavail_N.tif')
        forage._calc_available_nutrient(
            pft_i, iel, pft_param_dict, sv_reg, site_param_table,
            site_index_path, availm_path, favail_path, tgprod_path,
            eavail_path)

        self.assert_all_values_in_raster_within_range(
            eavail_path, known_N_avail - tolerance,
            known_N_avail + tolerance, _TARGET_NODATA)

        iel = 2
        eavail_path = os.path.join(self.workspace_dir, 'eavail_P.tif')
        forage._calc_available_nutrient(
            pft_i, iel, pft_param_dict, sv_reg, site_param_table,
            site_index_path, availm_path, favail_path, tgprod_path,
            eavail_path)

        self.assert_all_values_in_raster_within_range(
            eavail_path, known_P_avail - tolerance,
            known_P_avail + tolerance, _TARGET_NODATA)

    def test_calc_nutrient_demand(self):
        """Test `_calc_nutrient_demand`.

        Use the function `_calc_nutrient_demand` to calculate demand for
        one nutrient by one plant functional type. Test that the calculated
        demand is in the range [???].  Introduce nodata values into inputs
        and test that calculated demand remains in the range [???]. Test
        against a result calculated by hand for known inputs.

        Raises:
            AssertionError if demand from random inputs is outside the
                known possible range given the range of inputs
            AssertionError if demand from known inputs is outside the range
                [known result += 0.0001]

        Returns:
            None

        """
        from rangeland_production import forage

        biomass_production_path = os.path.join(
            self.workspace_dir, 'biomass_production.tif')
        fraction_allocated_to_roots_path = os.path.join(
            self.workspace_dir, 'fraction_allocated_to_roots.tif')
        cercrp_min_above_path = os.path.join(
            self.workspace_dir, 'cercrp_min_above.tif')
        cercrp_min_below_path = os.path.join(
            self.workspace_dir, 'cercrp_min_below.tif')
        demand_path = os.path.join(
            self.workspace_dir, 'demand.tif')

        # run with random inputs
        create_random_raster(biomass_production_path, 0, 675)
        create_random_raster(fraction_allocated_to_roots_path, 0.01, 0.99)
        create_random_raster(cercrp_min_above_path, 8, 16)
        create_random_raster(cercrp_min_below_path, 8, 16)

        minimum_acceptable_demand = 0
        maximum_acceptable_demand = 33.75

        forage._calc_nutrient_demand(
            biomass_production_path, fraction_allocated_to_roots_path,
            cercrp_min_above_path, cercrp_min_below_path, demand_path)

        self.assert_all_values_in_raster_within_range(
            demand_path, minimum_acceptable_demand,
            maximum_acceptable_demand, _TARGET_NODATA)

        # insert nodata values into inputs
        insert_nodata_values_into_raster(
            biomass_production_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(
            fraction_allocated_to_roots_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(cercrp_min_above_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(cercrp_min_below_path, _TARGET_NODATA)

        forage._calc_nutrient_demand(
            biomass_production_path, fraction_allocated_to_roots_path,
            cercrp_min_above_path, cercrp_min_below_path, demand_path)

        self.assert_all_values_in_raster_within_range(
            demand_path, minimum_acceptable_demand,
            maximum_acceptable_demand, _TARGET_NODATA)

        # run with known inputs
        create_random_raster(biomass_production_path, 300, 300)
        create_random_raster(fraction_allocated_to_roots_path, 0.4, 0.4)
        create_random_raster(cercrp_min_above_path, 15, 15)
        create_random_raster(cercrp_min_below_path, 9, 9)

        known_demand = 10.1333
        tolerance = 0.0001

        forage._calc_nutrient_demand(
            biomass_production_path, fraction_allocated_to_roots_path,
            cercrp_min_above_path, cercrp_min_below_path, demand_path)

        self.assert_all_values_in_raster_within_range(
            demand_path, known_demand - tolerance, known_demand + tolerance,
            _TARGET_NODATA)

    def test_calc_provisional_fracrc(self):
        """Test `calc_provisional_fracrc`.

        Use the function `calc_provisional_fracrc` to calculate fracrc_p, the
        fraction of carbon allocated to roots. Test that fracrc_p calculated
        from random inputs is inside the valid range given the range
        of inputs. Introduce nodata values into inputs and test that fracrc_p
        remains inside the valid range. Test the function with known inputs
        against values calculated by hand.

        Raises:
            AssertionError if fracrc_p from random inputs is outside the range
                of valid values given the range of inputs
            AssertionError if fracrc_p from known inputs is not within 0.0001
                of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        array_shape = (10, 10)

        annual_precip = numpy.random.uniform(22, 100, array_shape)
        frtcindx = numpy.random.randint(0, 2, array_shape)
        bgppa = numpy.random.uniform(100, 200, array_shape)
        bgppb = numpy.random.uniform(2, 12, array_shape)
        agppa = numpy.random.uniform(-40, -10, array_shape)
        agppb = numpy.random.uniform(2, 12, array_shape)
        cfrtcw_1 = numpy.random.uniform(0.4, 0.8, array_shape)
        cfrtcw_2 = numpy.random.uniform(0.01, 0.38, array_shape)
        cfrtcn_1 = numpy.random.uniform(0.4, 0.8, array_shape)
        cfrtcn_2 = numpy.random.uniform(0.01, 0.38, array_shape)

        minimum_acceptable_fracrc_p = 0.205
        maximum_acceptable_fracrc_p = 0.97297

        fracrc_p = forage.calc_provisional_fracrc(
            annual_precip, frtcindx, bgppa, bgppb, agppa, agppb,
            cfrtcw_1, cfrtcw_2, cfrtcn_1, cfrtcn_2)
        self.assert_all_values_in_array_within_range(
            fracrc_p, minimum_acceptable_fracrc_p,
            maximum_acceptable_fracrc_p, _TARGET_NODATA)

        insert_nodata_values_into_array(annual_precip, _TARGET_NODATA)
        fracrc_p = forage.calc_provisional_fracrc(
            annual_precip, frtcindx, bgppa, bgppb, agppa, agppb,
            cfrtcw_1, cfrtcw_2, cfrtcn_1, cfrtcn_2)
        self.assert_all_values_in_array_within_range(
            fracrc_p, minimum_acceptable_fracrc_p,
            maximum_acceptable_fracrc_p, _TARGET_NODATA)

        # known values
        annual_precip = numpy.full(array_shape, 42)
        bgppa = numpy.full(array_shape, 101)
        bgppb = numpy.full(array_shape, 4.2)
        agppa = numpy.full(array_shape, -12)
        agppb = numpy.full(array_shape, 3.2)
        cfrtcw_1 = numpy.full(array_shape, 0.4)
        cfrtcw_2 = numpy.full(array_shape, 0.33)
        cfrtcn_1 = numpy.full(array_shape, 0.76)
        cfrtcn_2 = numpy.full(array_shape, 0.02)

        insert_nodata_values_into_array(annual_precip, _TARGET_NODATA)

        known_fracrc_p_frtcindx_0 = 0.69385
        known_fracrc_p_frtcindx_1 = 0.3775
        tolerance = 0.0001

        frtcindx = numpy.full(array_shape, 0)
        fracrc_p = forage.calc_provisional_fracrc(
            annual_precip, frtcindx, bgppa, bgppb, agppa, agppb,
            cfrtcw_1, cfrtcw_2, cfrtcn_1, cfrtcn_2)
        self.assert_all_values_in_array_within_range(
            fracrc_p, known_fracrc_p_frtcindx_0 - tolerance,
            known_fracrc_p_frtcindx_0 + tolerance, _TARGET_NODATA)

        frtcindx = numpy.full(array_shape, 1)
        fracrc_p = forage.calc_provisional_fracrc(
            annual_precip, frtcindx, bgppa, bgppb, agppa, agppb,
            cfrtcw_1, cfrtcw_2, cfrtcn_1, cfrtcn_2)
        self.assert_all_values_in_array_within_range(
            fracrc_p, known_fracrc_p_frtcindx_1 - tolerance,
            known_fracrc_p_frtcindx_1 + tolerance, _TARGET_NODATA)

    def test_calc_ce_ratios(self):
        """Test `calc_ce_ratios`.

        Use the funciton `calc_ce_ratios` to calculate minimum and maximum
        carbon to nutrient ratios. Test that ratios calculated from random
        inputs are within the range of valid values given the range of
        inputs. Introduce nodata values into inputs and test that results
        remain within valid ranges. Calculate the ratios from known inputs
        against results calculated by hand.

        Raises:
            AssertionError if calculated ratios are outside the range of
                valid results given range of random inputs
            AssertionError if calculated ratios are not within 0.0001 of
                values calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        pramn_1_path = os.path.join(self.workspace_dir, 'pramn_1.tif')
        pramn_2_path = os.path.join(self.workspace_dir, 'pramn_2.tif')
        aglivc_path = os.path.join(self.workspace_dir, 'aglivc.tif')
        biomax_path = os.path.join(self.workspace_dir, 'biomax.tif')
        pramx_1_path = os.path.join(self.workspace_dir, 'pramx_1.tif')
        pramx_2_path = os.path.join(self.workspace_dir, 'pramx_2.tif')
        prbmn_1_path = os.path.join(self.workspace_dir, 'prbmn_1.tif')
        prbmn_2_path = os.path.join(self.workspace_dir, 'prbmn_2.tif')
        prbmx_1_path = os.path.join(self.workspace_dir, 'prbmx_1.tif')
        prbmx_2_path = os.path.join(self.workspace_dir, 'prbmx_2.tif')
        annual_precip_path = os.path.join(
            self.workspace_dir, 'annual_precip.tif')
        create_random_raster(pramn_1_path, 20, 50)
        create_random_raster(pramn_2_path, 52, 70)
        create_random_raster(aglivc_path, 20, 400)
        create_random_raster(biomax_path, 300, 500)
        create_random_raster(pramx_1_path, 51, 100)
        create_random_raster(pramx_2_path, 70, 130)
        create_random_raster(prbmn_1_path, 30, 70)
        create_random_raster(prbmn_2_path, 0, 0.2)
        create_random_raster(prbmx_1_path, 40, 70)
        create_random_raster(prbmx_2_path, 0, 0.4)
        create_random_raster(annual_precip_path, 22, 100)

        pft_i = numpy.random.randint(0, 5)
        iel = numpy.random.randint(1, 3)

        month_reg = {
            'cercrp_min_above_{}_{}'.format(iel, pft_i): os.path.join(
                self.workspace_dir,
                'cercrp_min_above_{}_{}.tif'.format(iel, pft_i)),
            'cercrp_max_above_{}_{}'.format(iel, pft_i): os.path.join(
                self.workspace_dir,
                'cercrp_max_above_{}_{}.tif'.format(iel, pft_i)),
            'cercrp_min_below_{}_{}'.format(iel, pft_i): os.path.join(
                self.workspace_dir,
                'cercrp_min_below_{}_{}.tif'.format(iel, pft_i)),
            'cercrp_max_below_{}_{}'.format(iel, pft_i): os.path.join(
                self.workspace_dir,
                'cercrp_max_below_{}_{}.tif'.format(iel, pft_i)),
        }

        acceptable_range_dict = {
            'cercrp_min_above_{}_{}'.format(iel, pft_i): {
                'minimum_acceptable_value': 25.3333,
                'maximum_acceptable_value': 70.,
            },
            'cercrp_max_above_{}_{}'.format(iel, pft_i): {
                'minimum_acceptable_value': 25.,
                'maximum_acceptable_value': 130.,
            },
            'cercrp_min_below_{}_{}'.format(iel, pft_i): {
                'minimum_acceptable_value': 30.,
                'maximum_acceptable_value': 90.,
            },
            'cercrp_max_below_{}_{}'.format(iel, pft_i): {
                'minimum_acceptable_value': 40.,
                'maximum_acceptable_value': 110.,
            },
        }
        forage.calc_ce_ratios(
            pramn_1_path, pramn_2_path, aglivc_path, biomax_path,
            pramx_1_path, pramx_2_path, prbmn_1_path, prbmn_2_path,
            prbmx_1_path, prbmx_2_path, annual_precip_path, pft_i, iel,
            month_reg)
        for path, ranges in acceptable_range_dict.items():
            self.assert_all_values_in_raster_within_range(
                month_reg[path], ranges['minimum_acceptable_value'],
                ranges['maximum_acceptable_value'], _TARGET_NODATA)

        insert_nodata_values_into_raster(aglivc_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(prbmn_1_path, _IC_NODATA)
        insert_nodata_values_into_raster(annual_precip_path, _TARGET_NODATA)
        forage.calc_ce_ratios(
            pramn_1_path, pramn_2_path, aglivc_path, biomax_path,
            pramx_1_path, pramx_2_path, prbmn_1_path, prbmn_2_path,
            prbmx_1_path, prbmx_2_path, annual_precip_path, pft_i, iel,
            month_reg)
        for path, ranges in acceptable_range_dict.items():
            self.assert_all_values_in_raster_within_range(
                month_reg[path], ranges['minimum_acceptable_value'],
                ranges['maximum_acceptable_value'], _TARGET_NODATA)

        # known inputs
        create_random_raster(pramn_1_path, 22, 22)
        create_random_raster(pramn_2_path, 55, 55)
        create_random_raster(aglivc_path, 321, 321)
        create_random_raster(biomax_path, 300, 300)
        create_random_raster(pramx_1_path, 46, 46)
        create_random_raster(pramx_2_path, 78, 78)
        create_random_raster(prbmn_1_path, 52, 52)
        create_random_raster(prbmn_2_path, 0.18, 0.18)
        create_random_raster(prbmx_1_path, 42, 42)
        create_random_raster(prbmx_2_path, 0.33, 0.33)
        create_random_raster(annual_precip_path, 77.22, 77.22)

        known_value_dict = {
            'cercrp_min_above_{}_{}'.format(iel, pft_i): 55.,
            'cercrp_max_above_{}_{}'.format(iel, pft_i): 78.,
            'cercrp_min_below_{}_{}'.format(iel, pft_i): 65.8996,
            'cercrp_max_below_{}_{}'.format(iel, pft_i): 67.4826,
        }
        tolerance = 0.0001

        insert_nodata_values_into_raster(aglivc_path, _SV_NODATA)
        insert_nodata_values_into_raster(prbmn_1_path, _IC_NODATA)
        insert_nodata_values_into_raster(annual_precip_path, _TARGET_NODATA)
        forage.calc_ce_ratios(
            pramn_1_path, pramn_2_path, aglivc_path, biomax_path,
            pramx_1_path, pramx_2_path, prbmn_1_path, prbmn_2_path,
            prbmx_1_path, prbmx_2_path, annual_precip_path, pft_i, iel,
            month_reg)
        for path, value in known_value_dict.items():
            self.assert_all_values_in_raster_within_range(
                month_reg[path], value - tolerance,
                value + tolerance, _TARGET_NODATA)

    def test_calc_revised_fracrc(self):
        """Test `calc_revised_fracrc`.

        Use the function `calc_revised_fracrc` to calculate fracrc_r, the
        revised fraction of carbon allocated to roots. Test that fracrc_r
        calculated from random inputs is within the range of valid values
        according to the range of inputs. Introduce nodata values into
        inputs and test that fracrc_r remains within the valid range.
        Test fracrc_r calculated from known inputs against the result
        calculated by hand.

        Raises:
            AssertionError if fracrc_r calculated from random inputs is
                outside the range of valid values
            AssertionError if fracrc_r from known inputs is not within
                0.0001 of the value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        frtcindx_path = os.path.join(self.workspace_dir, 'frtcindx.tif')
        fracrc_p_path = os.path.join(self.workspace_dir, 'fracrc_p.tif')
        totale_1_path = os.path.join(self.workspace_dir, 'totale_1.tif')
        totale_2_path = os.path.join(self.workspace_dir, 'totale_2.tif')
        demand_1_path = os.path.join(self.workspace_dir, 'demand_1.tif')
        demand_2_path = os.path.join(self.workspace_dir, 'demand_2.tif')
        h2ogef_1_path = os.path.join(self.workspace_dir, 'h2ogef_1.tif')
        cfrtcw_1_path = os.path.join(self.workspace_dir, 'cfrtcw_1.tif')
        cfrtcw_2_path = os.path.join(self.workspace_dir, 'cfrtcw_2.tif')
        cfrtcn_1_path = os.path.join(self.workspace_dir, 'cfrtcn_1.tif')
        cfrtcn_2_path = os.path.join(self.workspace_dir, 'cfrtcn_2.tif')
        fracrc_r_path = os.path.join(self.workspace_dir, 'fracrc_r.tif')

        create_random_raster(fracrc_p_path, 0.2, 0.95)
        create_random_raster(totale_1_path, 0, 320)
        create_random_raster(totale_2_path, 0, 52)
        create_random_raster(demand_1_path, 1, 34)
        create_random_raster(demand_2_path, 1, 34)
        create_random_raster(h2ogef_1_path, 0.01, 0.9)
        create_random_raster(cfrtcw_1_path, 0.4, 0.8)
        create_random_raster(cfrtcw_2_path, 1.01, 0.39)
        create_random_raster(cfrtcn_1_path, 0.4, 0.8)
        create_random_raster(cfrtcn_2_path, 1.01, 0.39)

        minimum_acceptable_fracrc_r = 0.01
        maximum_acceptable_fracrc_r = 0.999

        create_random_raster(frtcindx_path, 0, 0)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, minimum_acceptable_fracrc_r,
            maximum_acceptable_fracrc_r, _TARGET_NODATA)

        create_random_raster(frtcindx_path, 1, 1)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, minimum_acceptable_fracrc_r,
            maximum_acceptable_fracrc_r, _TARGET_NODATA)

        insert_nodata_values_into_raster(fracrc_p_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(totale_2_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(demand_1_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(cfrtcw_2_path, _IC_NODATA)

        create_random_raster(frtcindx_path, 0, 0)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, minimum_acceptable_fracrc_r,
            maximum_acceptable_fracrc_r, _TARGET_NODATA)

        create_random_raster(frtcindx_path, 1, 1)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, minimum_acceptable_fracrc_r,
            maximum_acceptable_fracrc_r, _TARGET_NODATA)

        # known values
        create_random_raster(fracrc_p_path, 0.7, 0.7)
        create_random_raster(totale_1_path, 10, 10)
        create_random_raster(totale_2_path, 157, 157)
        create_random_raster(demand_1_path, 14, 14)
        create_random_raster(demand_2_path, 30, 30)
        create_random_raster(h2ogef_1_path, 0.7, 0.7)
        create_random_raster(cfrtcw_1_path, 0.7, 0.7)
        create_random_raster(cfrtcw_2_path, 0.36, 0.36)
        create_random_raster(cfrtcn_1_path, 0.47, 0.47)
        create_random_raster(cfrtcn_2_path, 0.33, 0.33)

        known_fracrc_r_frtcindx_0 = 0.7
        known_fracrc_r_frtcindx_1 = 0.462
        tolerance = 0.0001

        create_random_raster(frtcindx_path, 0, 0)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, known_fracrc_r_frtcindx_0 - tolerance,
            known_fracrc_r_frtcindx_0 + tolerance, _TARGET_NODATA)

        create_random_raster(frtcindx_path, 1, 1)
        forage.calc_revised_fracrc(
            frtcindx_path, fracrc_p_path, totale_1_path, totale_2_path,
            demand_1_path, demand_2_path, h2ogef_1_path, cfrtcw_1_path,
            cfrtcw_2_path, cfrtcn_1_path, cfrtcn_2_path, fracrc_r_path)
        self.assert_all_values_in_raster_within_range(
            fracrc_r_path, known_fracrc_r_frtcindx_1 - tolerance,
            known_fracrc_r_frtcindx_1 + tolerance, _TARGET_NODATA)

    def test_grazing_effect(self):
        """Test `grazing_effect_on_aboveground_production`.

        Use the function `grazing_effect_on_aboveground_production` to
        calculate agprod, revised aboveground production including the
        effects of grazing. Use the function `grazing_effect_on_root_shoot` to
        calculate rtsh, root:shoot ratio including the effects of grazing.
        Test that agprod and rtsh match values calculated by hand. Introduce
        nodata values into inputs and ensure that calculated agprod and rtsh
        still match value calculated by hand.

        Raises:
            AssertionError if agprod is not within 0.0001 of value
                calculated by hand
            AssertionError if rtsh if not within 0.0001 of value calculated by
                hand

        Returns:
            None

        """
        from rangeland_production import forage

        array_shape = (3, 3)

        # known values
        tgprod = numpy.full(array_shape, 500)
        fracrc = numpy.full(array_shape, 0.62)
        flgrem = numpy.full(array_shape, 0.16)
        gremb = numpy.full(array_shape, 0.02)

        tolerance = 0.0001

        grzeff = numpy.full(array_shape, 1)
        agprod_grzeff_1 = 122.816
        rtsh_grzeff_1 = 1.63158
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_1 - tolerance, agprod_grzeff_1 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_1 - tolerance, rtsh_grzeff_1 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 2)
        agprod_grzeff_2 = 240.6828
        rtsh_grzeff_2 = 1.818
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_2 - tolerance, agprod_grzeff_2 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_2 - tolerance, rtsh_grzeff_2 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 3)
        agprod_grzeff_3 = 190
        rtsh_grzeff_3 = 1.818
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_3 - tolerance, agprod_grzeff_3 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_3 - tolerance, rtsh_grzeff_3 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 4)
        agprod_grzeff_4 = 190
        rtsh_grzeff_4 = 0.9968
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_4 - tolerance, agprod_grzeff_4 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_4 - tolerance, rtsh_grzeff_4 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 5)
        agprod_grzeff_5 = 240.6828
        rtsh_grzeff_5 = 0.9968
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_5 - tolerance, agprod_grzeff_5 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_5 - tolerance, rtsh_grzeff_5 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 6)
        agprod_grzeff_6 = 122.816
        rtsh_grzeff_6 = 0.9968
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_6 - tolerance, agprod_grzeff_6 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_6 - tolerance, rtsh_grzeff_6 + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(fracrc, _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 4)
        agprod_grzeff_4 = 190
        rtsh_grzeff_4 = 0.9968
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_4 - tolerance, agprod_grzeff_4 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_4 - tolerance, rtsh_grzeff_4 + tolerance,
            _TARGET_NODATA)

        grzeff = numpy.full(array_shape, 2)
        agprod_grzeff_2 = 240.6828
        rtsh_grzeff_2 = 1.818
        agprod = forage.grazing_effect_on_aboveground_production(
            tgprod, fracrc, flgrem, grzeff)
        rtsh = forage.grazing_effect_on_root_shoot(
            fracrc, flgrem, grzeff, gremb)
        self.assert_all_values_in_array_within_range(
            agprod, agprod_grzeff_2 - tolerance, agprod_grzeff_2 + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            rtsh, rtsh_grzeff_2 - tolerance, rtsh_grzeff_2 + tolerance,
            _TARGET_NODATA)

    def test_calc_tgprod_final(self):
        """Test `calc_tgprod_final`.

        Use the function `calc_tgprod_final` to calculate tgprod, final total
        prodcution from root:shoot ratio and aboveground production. Test that
        calculated tgprod matches results calculated by hand.

        Raises:
            AssertionError if tgprod is not within 0.0001 of the value
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        array_size = (3, 3)
        # known values
        rtsh = numpy.full(array_size, 0.72)
        agprod = numpy.full(array_size, 333)

        known_tgprod = 572.76
        tolerance = 0.0001
        tgprod = forage.calc_tgprod_final(rtsh, agprod)
        self.assert_all_values_in_array_within_range(
            tgprod, known_tgprod - tolerance, known_tgprod + tolerance,
            _TARGET_NODATA)

    def test_snow(self):
        """Test `_snow`.

        Use the function `_snow` to modify snow pack, evaporate from snow pack,
        melt snow, and determine liquid inputs to soil after snow. Test
        the raster-based function against a point-based function defined
        here.

        Raises:
            AssertionError if raster-based outputs do not match outputs
                calculated by point-based version

        Returns:
            None

        """
        def snow_point(
                precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
                shwave):
            """Point-based implementation of `_snow`.

            This implementation reproduces Century's process for determining
            snowfall, evaporation from snow, snowmelt, and liquid draining
            into soil after snow is accounted.

            Parameters:
                precip (float): precipitation this month
                max_temp (float): maximum temperature this month
                min_temp (float): minimum temperature this month
                snow (float): existing snow prior to new precipitation
                snlq (float): existing liquid in snow prior to new
                    precipitation
                pet (float): potential evapotranspiration
                tmelt_1 (float): parameter, temperature above which some
                    snow melts
                tmelt_2 (float): parameter, ratio between degrees above the
                    minimum temperature and cm of snow that will melt

            Returns:
                dict of modified quantities: snowmelt, snow, snlq, pet,
                inputs_after_snow

            """
            tave = (max_temp + min_temp) / 2.
            inputs_after_snow = precip
            # precip falls as snow when temperature is below freezing
            if tave <= 0:
                snow = snow + precip
                # all precip is snow, none left
                inputs_after_snow = 0
            else:
                if snow > 0:
                    snlq = snlq + precip
                    # all precip is rain on snow, none left
                    inputs_after_snow = 0

            snowmelt = 0
            if snow > 0:
                snowtot = snow + snlq
                evsnow = min(snowtot, (pet * 0.87))
                snow = max(snow - evsnow * (snow/snowtot), 0.)
                snlq = max(snlq-evsnow * (snlq/snowtot), 0.)
                pet = max((pet - evsnow / 0.87), 0)

                if tave >= tmelt_1:
                    snowmelt = tmelt_2 * (tave - tmelt_1) * shwave
                    snowmelt = max(snowmelt, 0)
                    snowmelt = min(snowmelt, snow)
                    snow = snow - snowmelt
                    snlq = snlq + snowmelt
                    if snlq > (0.5 * snow):
                        add = snlq - 0.5 * snow
                        snlq = snlq - add
                        inputs_after_snow = add

            results_dict = {
                'snowmelt': snowmelt,
                'snow': snow,
                'snlq': snlq,
                'pet': pet,
                'inputs_after_snow': inputs_after_snow,
            }
            return results_dict

        from rangeland_production import forage

        # shortwave radiation and pet calculated by hand
        CURRENT_MONTH = 10
        SHWAVE = 437.04
        TMELT_1 = 0.
        TMELT_2 = 0.002
        FWLOSS_4 = 0.6

        # rain on snow, all snow melts
        test_dict = {
            'precip': 15.,
            'max_temp': 23.,
            'min_temp': -2.,
            'snow': 8.,
            'snlq': 4.,
            'pet': 4.967985,
            'tmelt_1': TMELT_1,
            'tmelt_2': TMELT_2,
            'shwave': SHWAVE,
        }
        test_dict['tave'] = (test_dict['max_temp'] + test_dict['min_temp']) / 2

        site_param_table = {
            1: {
                'tmelt_1': TMELT_1,
                'tmelt_2': TMELT_2,
                'fwloss_4': FWLOSS_4,
            }
        }
        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')
        precip_path = os.path.join(self.workspace_dir, 'precip.tif')
        tave_path = os.path.join(self.workspace_dir, 'tave.tif')
        max_temp_path = os.path.join(self.workspace_dir, 'max_temp.tif')
        min_temp_path = os.path.join(self.workspace_dir, 'min_temp.tif')
        prev_snow_path = os.path.join(self.workspace_dir, 'prev_snow.tif')
        prev_snlq_path = os.path.join(self.workspace_dir, 'prev_snlq.tif')
        snowmelt_path = os.path.join(self.workspace_dir, 'snowmelt.tif')
        snow_path = os.path.join(self.workspace_dir, 'snow.tif')
        snlq_path = os.path.join(self.workspace_dir, 'snlq.tif')
        inputs_after_snow_path = os.path.join(
            self.workspace_dir, 'inputs_after_snow.tif')
        pet_rem_path = os.path.join(self.workspace_dir, 'pet_rem.tif')

        # raster inputs
        nrows = 1
        ncols = 1
        create_random_raster(site_index_path, 1, 1, nrows=nrows, ncols=ncols)
        create_random_raster(
            precip_path, test_dict['precip'], test_dict['precip'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            tave_path, test_dict['tave'], test_dict['tave'], nrows=nrows,
            ncols=ncols)
        create_random_raster(
            max_temp_path, test_dict['max_temp'], test_dict['max_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            min_temp_path, test_dict['min_temp'], test_dict['min_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snow_path, test_dict['snow'], test_dict['snow'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snlq_path, test_dict['snlq'], test_dict['snlq'],
            nrows=nrows, ncols=ncols)

        tolerance = 0.000015
        result_dict = snow_point(
            test_dict['precip'], test_dict['max_temp'], test_dict['min_temp'],
            test_dict['snow'], test_dict['snlq'], test_dict['pet'],
            test_dict['tmelt_1'], test_dict['tmelt_2'], SHWAVE)

        forage._snow(
            site_index_path, site_param_table, precip_path, tave_path,
            max_temp_path, min_temp_path, prev_snow_path, prev_snlq_path,
            CURRENT_MONTH, snowmelt_path, snow_path, snlq_path,
            inputs_after_snow_path, pet_rem_path)

        self.assert_all_values_in_raster_within_range(
            pet_rem_path, result_dict['pet'] - tolerance,
            result_dict['pet'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snowmelt_path, result_dict['snowmelt'] - tolerance,
            result_dict['snowmelt'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snow_path, result_dict['snow'], result_dict['snow'],
            _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snlq_path, result_dict['snlq'], result_dict['snlq'],
            _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            inputs_after_snow_path,
            result_dict['inputs_after_snow'] - tolerance,
            result_dict['inputs_after_snow'] + tolerance, _TARGET_NODATA)

        # new snowfall, no snowmelt
        test_dict = {
            'precip': 15.,
            'max_temp': 2.,
            'min_temp': -6.,
            'snow': 2.,
            'snlq': 1.,
            'pet': 1.5690107,
            'tmelt_1': TMELT_1,
            'tmelt_2': TMELT_2,
            'shwave': SHWAVE,
        }
        test_dict['tave'] = (test_dict['max_temp'] + test_dict['min_temp']) / 2

        create_random_raster(site_index_path, 1, 1, nrows=nrows, ncols=ncols)
        create_random_raster(
            precip_path, test_dict['precip'], test_dict['precip'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            tave_path, test_dict['tave'], test_dict['tave'], nrows=nrows,
            ncols=ncols)
        create_random_raster(
            max_temp_path, test_dict['max_temp'], test_dict['max_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            min_temp_path, test_dict['min_temp'], test_dict['min_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snow_path, test_dict['snow'], test_dict['snow'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snlq_path, test_dict['snlq'], test_dict['snlq'],
            nrows=nrows, ncols=ncols)

        result_dict = snow_point(
            test_dict['precip'], test_dict['max_temp'], test_dict['min_temp'],
            test_dict['snow'], test_dict['snlq'], test_dict['pet'],
            test_dict['tmelt_1'], test_dict['tmelt_2'], SHWAVE)

        forage._snow(
            site_index_path, site_param_table, precip_path, tave_path,
            max_temp_path, min_temp_path, prev_snow_path, prev_snlq_path,
            CURRENT_MONTH, snowmelt_path, snow_path, snlq_path,
            inputs_after_snow_path, pet_rem_path)

        self.assert_all_values_in_raster_within_range(
            snowmelt_path, result_dict['snowmelt'] - tolerance,
            result_dict['snowmelt'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snow_path, result_dict['snow'] - tolerance,
            result_dict['snow'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snlq_path, result_dict['snlq'] - tolerance,
            result_dict['snlq'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            inputs_after_snow_path, result_dict['inputs_after_snow'],
            result_dict['inputs_after_snow'], _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            pet_rem_path, result_dict['pet'], result_dict['pet'],
            _TARGET_NODATA)

        # new snowfall, some snowmelt
        test_dict = {
            'precip': 10.,
            'max_temp': 2.,
            'min_temp': -2.01,
            'snow': 2.,
            'snlq': 1.,
            'pet': 1.2511096,
            'tmelt_1': TMELT_1,
            'tmelt_2': TMELT_2,
            'shwave': SHWAVE,
        }
        test_dict['tave'] = (test_dict['max_temp'] + test_dict['min_temp']) / 2

        create_random_raster(site_index_path, 1, 1, nrows=nrows, ncols=ncols)
        create_random_raster(
            precip_path, test_dict['precip'], test_dict['precip'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            tave_path, test_dict['tave'], test_dict['tave'], nrows=nrows,
            ncols=ncols)
        create_random_raster(
            max_temp_path, test_dict['max_temp'], test_dict['max_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            min_temp_path, test_dict['min_temp'], test_dict['min_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snow_path, test_dict['snow'], test_dict['snow'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snlq_path, test_dict['snlq'], test_dict['snlq'],
            nrows=nrows, ncols=ncols)

        result_dict = snow_point(
            test_dict['precip'], test_dict['max_temp'], test_dict['min_temp'],
            test_dict['snow'], test_dict['snlq'], test_dict['pet'],
            test_dict['tmelt_1'], test_dict['tmelt_2'], SHWAVE)

        forage._snow(
            site_index_path, site_param_table, precip_path, tave_path,
            max_temp_path, min_temp_path, prev_snow_path, prev_snlq_path,
            CURRENT_MONTH, snowmelt_path, snow_path, snlq_path,
            inputs_after_snow_path, pet_rem_path)

        self.assert_all_values_in_raster_within_range(
            snowmelt_path, result_dict['snowmelt'] - tolerance,
            result_dict['snowmelt'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snow_path, result_dict['snow'] - tolerance,
            result_dict['snow'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snlq_path, result_dict['snlq'] - tolerance,
            result_dict['snlq'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            inputs_after_snow_path,
            result_dict['inputs_after_snow'],
            result_dict['inputs_after_snow'], _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            pet_rem_path, result_dict['pet'] - tolerance,
            result_dict['pet'] + tolerance, _TARGET_NODATA)

        # no snow, no snowfall
        test_dict = {
            'precip': 10.,
            'max_temp': 23.,
            'min_temp': -2.,
            'snow': 0.,
            'snlq': 0.,
            'pet': 4.9680004,
            'tmelt_1': TMELT_1,
            'tmelt_2': TMELT_2,
            'shwave': 457.95056,
        }
        test_dict['tave'] = (test_dict['max_temp'] + test_dict['min_temp']) / 2

        create_random_raster(site_index_path, 1, 1, nrows=nrows, ncols=ncols)
        create_random_raster(
            precip_path, test_dict['precip'], test_dict['precip'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            tave_path, test_dict['tave'], test_dict['tave'], nrows=nrows,
            ncols=ncols)
        create_random_raster(
            max_temp_path, test_dict['max_temp'], test_dict['max_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            min_temp_path, test_dict['min_temp'], test_dict['min_temp'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snow_path, test_dict['snow'], test_dict['snow'],
            nrows=nrows, ncols=ncols)
        create_random_raster(
            prev_snlq_path, test_dict['snlq'], test_dict['snlq'],
            nrows=nrows, ncols=ncols)

        result_dict = snow_point(
            test_dict['precip'], test_dict['max_temp'], test_dict['min_temp'],
            test_dict['snow'], test_dict['snlq'], test_dict['pet'],
            test_dict['tmelt_1'], test_dict['tmelt_2'], SHWAVE)

        forage._snow(
            site_index_path, site_param_table, precip_path, tave_path,
            max_temp_path, min_temp_path, prev_snow_path, prev_snlq_path,
            CURRENT_MONTH, snowmelt_path, snow_path, snlq_path,
            inputs_after_snow_path, pet_rem_path)

        self.assert_all_values_in_raster_within_range(
            snowmelt_path, result_dict['snowmelt'] - tolerance,
            result_dict['snowmelt'] + tolerance, _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snow_path, result_dict['snow'], result_dict['snow'],
            _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            snlq_path, result_dict['snlq'], result_dict['snlq'],
            _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            inputs_after_snow_path, result_dict['inputs_after_snow'],
            result_dict['inputs_after_snow'], _TARGET_NODATA)

        self.assert_all_values_in_raster_within_range(
            pet_rem_path, result_dict['pet'] - tolerance,
            result_dict['pet'] + tolerance, _TARGET_NODATA)

    def test_calc_aboveground_live_biomass(self):
        """Test `_calc_aboveground_live_biomass`.

        Use the function `_calc_aboveground_live_biomass` to calculate
        aboveground live biomass for the purposes of soil water. Test that the
        function reproduces results calculated by hand.

        Raises:
            AssertionError if `_calc_aboveground_live_biomass` does not match
                results calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        array_size = (3, 3)
        # known values
        sum_aglivc = numpy.full(array_size, 200.)
        sum_tgprod = numpy.full(array_size, 180.)

        known_aliv = 545.
        tolerance = 0.00001
        aliv = forage._calc_aboveground_live_biomass(sum_aglivc, sum_tgprod)
        self.assert_all_values_in_array_within_range(
            aliv, known_aliv - tolerance, known_aliv + tolerance,
            _TARGET_NODATA)

    def test_calc_standing_biomass(self):
        """Test `_calc_standing_biomass`.

        Use the function `_calc_standing_biomass` to calculate total
        aboveground standing biomass for soil water. Test that the function
        reproduces results calculated by hand.

        Raises:
            AssertionError if `_calc_standing_biomass` does not match results
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        array_size = (3, 3)
        # known values
        aliv = numpy.full(array_size, 545)
        sum_stdedc = numpy.full(array_size, 232)

        known_sd = 800.
        tolerance = 0.00001
        sd = forage._calc_standing_biomass(aliv, sum_stdedc)
        self.assert_all_values_in_array_within_range(
            sd, known_sd - tolerance, known_sd + tolerance, _TARGET_NODATA)

        # known values
        aliv = numpy.full(array_size, 233.2)
        sum_stdedc = numpy.full(array_size, 172)

        known_sd = 663.2
        tolerance = 0.0001
        sd = forage._calc_standing_biomass(aliv, sum_stdedc)
        self.assert_all_values_in_array_within_range(
            sd, known_sd - tolerance, known_sd + tolerance, _TARGET_NODATA)

    def test_subtract_surface_losses(self):
        """Test `subtract_surface_losses`.

        Use the function `subtract_surface_losses` to calculate moisture
        losses to runoff, canopy interception, and evaporation.  Test that
        the function reproduces results calculated by a point-based function
        defined here.

        Raises:
            AssertionError if `subtract_surface_losses` does not match
                point-based results calculated by test function

        Returns:
            None

        """
        def surface_losses_point(
                inputs_after_snow, fracro, precro, snow, alit, sd, fwloss_1,
                fwloss_2, pet_rem):
            """Point- based implementation of `subtract_surface_losses`.

            This implementation reproduces Century's process for determining
            loss of moisture inputs to runoff, canopy interception, and surface
            evaporation.

            Parameters:
                inputs_after_snow (float): surface water inputs from
                    precipitation and snowmelt, prior to runoff
                fracro (float): parameter, fraction of surface water
                    above precro that is lost to runoff
                precro (float): parameter, amount of surface water that
                    must be available for runoff to occur
                snow (float): current snowpack
                alit (float): biomass in surface litter
                sd (float): total standing biomass
                fwloss_1 (float): parameter, scaling factor for
                    interception and evaporation of precip by vegetation
                fwloss_2 (float): parameter, scaling factor for bare soil
                    evaporation of precip
                pet_rem (float): potential evaporation remaining after
                    evaporation of snow

            Returns:
                dict of modified quantities: inputs_after_surface, surface
                    water inputs to soil after runoff and surface evaporation
                    are subtracted; absevap, moisture lost to surface
                    evaporation; and evap_losses, total surface evaporation

            """
            runoff = max(fracro * (inputs_after_snow - precro), 0.)
            inputs_after_runoff = inputs_after_snow - runoff
            if snow == 0:
                aint = (0.0003 * alit + 0.0006 * sd) * fwloss_1
                absevap = (
                    0.5 * math.exp((-0.002 * alit) - (0.004 * sd)) * fwloss_2)
                evap_losses = min(
                    ((absevap + aint) * inputs_after_runoff), 0.4 * pet_rem)
            else:
                absevap = 0
                evap_losses = 0
            inputs_after_surface = inputs_after_runoff - evap_losses

            results_dict = {
                'inputs_after_surface': inputs_after_surface,
                'absevap': absevap,
                'evap_losses': evap_losses,
            }
            return results_dict

        from rangeland_production import forage
        array_size = (10, 10)

        # snow cover, runoff losses only
        test_dict = {
            'inputs_after_snow': 34.,
            'fracro': 0.15,
            'precro': 8.,
            'snow': 20.,
            'alit': 100.,
            'sd': 202.5,
            'fwloss_1': 0.9,
            'fwloss_2': 0.7,
            'pet_rem': 3.88,
        }

        inputs_after_snow = numpy.full(
            array_size, test_dict['inputs_after_snow'])
        fracro = numpy.full(array_size, test_dict['fracro'])
        precro = numpy.full(array_size, test_dict['precro'])
        snow = numpy.full(array_size, test_dict['snow'])
        alit = numpy.full(array_size, test_dict['alit'])
        sd = numpy.full(array_size, test_dict['sd'])
        fwloss_1 = numpy.full(array_size, test_dict['fwloss_1'])
        fwloss_2 = numpy.full(array_size, test_dict['fwloss_2'])
        pet_rem = numpy.full(array_size, test_dict['pet_rem'])

        result_dict = surface_losses_point(
            test_dict['inputs_after_snow'], test_dict['fracro'],
            test_dict['precro'], test_dict['snow'], test_dict['alit'],
            test_dict['sd'], test_dict['fwloss_1'], test_dict['fwloss_2'],
            test_dict['pet_rem'])
        tolerance = 0.00001
        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(pet_rem, _TARGET_NODATA)
        insert_nodata_values_into_array(snow, _TARGET_NODATA)
        insert_nodata_values_into_array(fracro, _IC_NODATA)

        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

        # no snow cover, large surface biomass
        test_dict = {
            'inputs_after_snow': 12.,
            'fracro': 0.15,
            'precro': 8.,
            'snow': 0.,
            'alit': 200.1,
            'sd': 800.,
            'fwloss_1': 0.8,
            'fwloss_2': 0.8,
            'pet_rem': 3.88,
        }

        inputs_after_snow = numpy.full(
            array_size, test_dict['inputs_after_snow'])
        fracro = numpy.full(array_size, test_dict['fracro'])
        precro = numpy.full(array_size, test_dict['precro'])
        snow = numpy.full(array_size, test_dict['snow'])
        alit = numpy.full(array_size, test_dict['alit'])
        sd = numpy.full(array_size, test_dict['sd'])
        fwloss_1 = numpy.full(array_size, test_dict['fwloss_1'])
        fwloss_2 = numpy.full(array_size, test_dict['fwloss_2'])
        pet_rem = numpy.full(array_size, test_dict['pet_rem'])

        result_dict = surface_losses_point(
            test_dict['inputs_after_snow'], test_dict['fracro'],
            test_dict['precro'], test_dict['snow'], test_dict['alit'],
            test_dict['sd'], test_dict['fwloss_1'], test_dict['fwloss_2'],
            test_dict['pet_rem'])
        tolerance = 0.00001
        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(alit, _TARGET_NODATA)
        insert_nodata_values_into_array(precro, _IC_NODATA)
        insert_nodata_values_into_array(fwloss_2, _IC_NODATA)

        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

        # no snow cover, small surface biomass
        test_dict = {
            'inputs_after_snow': 12.,
            'fracro': 0.15,
            'precro': 8.,
            'snow': 0.,
            'alit': 300.1,
            'sd': 80.5,
            'fwloss_1': 0.8,
            'fwloss_2': 0.8,
            'pet_rem': 4.99,
        }

        inputs_after_snow = numpy.full(
            array_size, test_dict['inputs_after_snow'])
        fracro = numpy.full(array_size, test_dict['fracro'])
        precro = numpy.full(array_size, test_dict['precro'])
        snow = numpy.full(array_size, test_dict['snow'])
        alit = numpy.full(array_size, test_dict['alit'])
        sd = numpy.full(array_size, test_dict['sd'])
        fwloss_1 = numpy.full(array_size, test_dict['fwloss_1'])
        fwloss_2 = numpy.full(array_size, test_dict['fwloss_2'])
        pet_rem = numpy.full(array_size, test_dict['pet_rem'])

        result_dict = surface_losses_point(
            test_dict['inputs_after_snow'], test_dict['fracro'],
            test_dict['precro'], test_dict['snow'], test_dict['alit'],
            test_dict['sd'], test_dict['fwloss_1'], test_dict['fwloss_2'],
            test_dict['pet_rem'])
        tolerance = 0.00001
        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(inputs_after_snow, _TARGET_NODATA)
        insert_nodata_values_into_array(fwloss_1, _IC_NODATA)
        insert_nodata_values_into_array(fwloss_2, _IC_NODATA)

        inputs_after_surface = forage.subtract_surface_losses(
            'inputs_after_surface')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        absevap = forage.subtract_surface_losses(
            'absevap')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)
        evap_losses = forage.subtract_surface_losses(
            'evap_losses')(
                inputs_after_snow, fracro, precro, snow,
                alit, sd, fwloss_1, fwloss_2, pet_rem)

        self.assert_all_values_in_array_within_range(
            inputs_after_surface,
            result_dict['inputs_after_surface'] - tolerance,
            result_dict['inputs_after_surface'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            absevap, result_dict['absevap'] - tolerance,
            result_dict['absevap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            evap_losses, result_dict['evap_losses'] - tolerance,
            result_dict['evap_losses'] + tolerance, _TARGET_NODATA)

    def test_calc_potential_transpiration(self):
        """Test `calc_potential_transpiration`.

        Use the function `calc_potential_transpiration` to calculate
        potential transpiration from the soil by plants, potential  evaporation
        of soil moisture from soil layer 1, initial transpiration water loss,
        and modified water inputs. Test the function against a point-based
        version defined here.

        Raises:
            AssertionError if point-based test version of
                `subtract_surface_losses` does not match values calculated by
                hand
            AssertionError if `subtract_surface_losses` does not match results
                calculated by point-based test version

        Returns:
            None

        """
        def potential_transpiration_point(
                pet_rem, evap_losses, tave, aliv, current_moisture_inputs):
            """Calculate trap, pevp, and modified moisture inputs.

            Parameters:
                pet_rem (float): potential evapotranspiration remaining after
                    evaporation of snow
                evap_losses (float): total surface evaporation
                tave (float): average temperature
                aliv (float): aboveground live biomass
                current_moisture_inputs (float): moisture inputs after surface
                    losses

            Returns:
                dict of moidified quantities: trap, potential transpiration;
                    pevp, potential evaporation from surface soil layer;
                    modified_moisture_inputs, water to be added to soil layers
                    before transpiration losses are accounted

            """
            trap = pet_rem - evap_losses
            if tave < 2:
                pttr = 0
            else:
                pttr = pet_rem * 0.65 * (1 - math.exp(-0.02 * aliv))
            if pttr <= trap:
                trap = pttr
            if trap <= 0:
                trap = 0.01
            pevp = max(pet_rem - trap - evap_losses, 0.)
            tran = min(trap - 0.01, current_moisture_inputs)
            trap = trap - tran
            modified_moisture_inputs = current_moisture_inputs - tran

            results_dict = {
                'trap': trap,
                'pevp': pevp,
                'modified_moisture_inputs': modified_moisture_inputs,
            }
            return results_dict

        from rangeland_production import forage
        array_size = (10, 10)

        # high transpiration limited by water inputs
        test_dict = {
            'pet_rem': 13.2,
            'evap_losses': 5.28,
            'tave': 22.3,
            'aliv': 100.,
            'current_moisture_inputs': 7.4,
        }

        pet_rem = numpy.full(array_size, test_dict['pet_rem'])
        evap_losses = numpy.full(array_size, test_dict['evap_losses'])
        tave = numpy.full(array_size, test_dict['tave'])
        aliv = numpy.full(array_size, test_dict['aliv'])
        current_moisture_inputs = numpy.full(
            array_size, test_dict['current_moisture_inputs'])

        result_dict = potential_transpiration_point(
            test_dict['pet_rem'], test_dict['evap_losses'], test_dict['tave'],
            test_dict['aliv'], test_dict['current_moisture_inputs'])

        insert_nodata_values_into_array(aliv, _TARGET_NODATA)
        insert_nodata_values_into_array(
            current_moisture_inputs, _TARGET_NODATA)
        insert_nodata_values_into_array(tave, _IC_NODATA)

        trap = forage.calc_potential_transpiration(
            'trap')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        pevp = forage.calc_potential_transpiration(
            'pevp')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        modified_moisture_inputs = forage.calc_potential_transpiration(
            'modified_moisture_inputs')(
            pet_rem, evap_losses, tave, aliv, current_moisture_inputs)

        # known values calculated by hand
        known_trap = 0.018823
        known_pevp = 0.50118
        known_modified_moisture_inputs = 0
        tolerance = 0.00001

        self.assertAlmostEqual(
            result_dict['trap'], known_trap, delta=tolerance,
            msg=(
                "trap calculated by point-based test version does not match" +
                " value calculated by hand"))
        self.assertAlmostEqual(
            result_dict['pevp'], known_pevp, delta=tolerance,
            msg=(
                "pevp calculated by point-based test version does not match" +
                " value calculated by hand"))
        self.assertAlmostEqual(
            result_dict['modified_moisture_inputs'],
            known_modified_moisture_inputs,
            delta=tolerance,
            msg=(
                "modified_moisture_inputs calculated by point-based test " +
                "version does not match value calculated by hand"))
        self.assert_all_values_in_array_within_range(
            trap, result_dict['trap'] - tolerance,
            result_dict['trap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            pevp, result_dict['pevp'] - tolerance,
            result_dict['pevp'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            modified_moisture_inputs,
            result_dict['modified_moisture_inputs'] - tolerance,
            result_dict['modified_moisture_inputs'] + tolerance,
            _TARGET_NODATA)

        # low temperature, no transpiration occurs
        test_dict = {
            'pet_rem': 3.24,
            'evap_losses': 1.12,
            'tave': 1.,
            'aliv': 180.,
            'current_moisture_inputs': 62.,
        }

        pet_rem = numpy.full(array_size, test_dict['pet_rem'])
        evap_losses = numpy.full(array_size, test_dict['evap_losses'])
        tave = numpy.full(array_size, test_dict['tave'])
        aliv = numpy.full(array_size, test_dict['aliv'])
        current_moisture_inputs = numpy.full(
            array_size, test_dict['current_moisture_inputs'])

        result_dict = potential_transpiration_point(
            test_dict['pet_rem'], test_dict['evap_losses'], test_dict['tave'],
            test_dict['aliv'], test_dict['current_moisture_inputs'])

        trap = forage.calc_potential_transpiration(
            'trap')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        pevp = forage.calc_potential_transpiration(
            'pevp')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        modified_moisture_inputs = forage.calc_potential_transpiration(
            'modified_moisture_inputs')(
            pet_rem, evap_losses, tave, aliv, current_moisture_inputs)

        self.assert_all_values_in_array_within_range(
            trap, result_dict['trap'] - tolerance,
            result_dict['trap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            pevp, result_dict['pevp'] - tolerance,
            result_dict['pevp'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            modified_moisture_inputs,
            result_dict['modified_moisture_inputs'] - tolerance,
            result_dict['modified_moisture_inputs'] + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(pet_rem, _TARGET_NODATA)
        insert_nodata_values_into_array(evap_losses, _TARGET_NODATA)
        insert_nodata_values_into_array(tave, _IC_NODATA)

        trap = forage.calc_potential_transpiration(
            'trap')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        pevp = forage.calc_potential_transpiration(
            'pevp')(pet_rem, evap_losses, tave, aliv, current_moisture_inputs)
        modified_moisture_inputs = forage.calc_potential_transpiration(
            'modified_moisture_inputs')(
            pet_rem, evap_losses, tave, aliv, current_moisture_inputs)

        self.assert_all_values_in_array_within_range(
            trap, result_dict['trap'] - tolerance,
            result_dict['trap'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            pevp, result_dict['pevp'] - tolerance,
            result_dict['pevp'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            modified_moisture_inputs,
            result_dict['modified_moisture_inputs'] - tolerance,
            result_dict['modified_moisture_inputs'] + tolerance,
            _TARGET_NODATA)

    def test_distribute_water_to_soil_layer(self):
        """Test `distribute_water_to_soil_layer`.

        Use the function `distribute_water_to_soil_layer` to revise moisture
        content in one soil layer and calculate the moisture added to the next
        adjacent soil layer.

        Raises:
            AssertionError if `distribute_water_to_soil_layer` does not match
            value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_size = (10, 10)
        tolerance = 0.00001

        # high moisture inputs, overflow to next soil layer
        adep = 13.68
        afiel = 0.32
        asmos = 3.1
        current_moisture_inputs = 8.291

        known_asmos_revised = 4.3776
        known_modified_moisture_inputs = 11.391

        adep_ar = numpy.full(array_size, adep)
        afiel_ar = numpy.full(array_size, afiel)
        asmos_ar = numpy.full(array_size, asmos)
        current_moisture_inputs_ar = numpy.full(
            array_size, current_moisture_inputs)

        insert_nodata_values_into_array(adep_ar, _IC_NODATA)
        insert_nodata_values_into_array(asmos_ar, _TARGET_NODATA)

        asmos_revised = forage.distribute_water_to_soil_layer(
            'asmos_revised')(
            adep_ar, afiel_ar, asmos_ar, current_moisture_inputs_ar)
        amov = forage.distribute_water_to_soil_layer(
            'amov')(adep_ar, afiel_ar, asmos_ar, current_moisture_inputs_ar)

        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            amov, known_modified_moisture_inputs - tolerance,
            known_modified_moisture_inputs + tolerance, _TARGET_NODATA)

        # high field capacity, no overflow
        adep = 17.
        afiel = 0.482
        asmos = 0.01
        current_moisture_inputs = 4.2

        known_asmos_revised = 4.21
        known_modified_moisture_inputs = 0

        adep_ar = numpy.full(array_size, adep)
        afiel_ar = numpy.full(array_size, afiel)
        asmos_ar = numpy.full(array_size, asmos)
        current_moisture_inputs_ar = numpy.full(
            array_size, current_moisture_inputs)

        insert_nodata_values_into_array(afiel_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(
            current_moisture_inputs_ar, _TARGET_NODATA)

        asmos_revised = forage.distribute_water_to_soil_layer(
            'asmos_revised')(
            adep_ar, afiel_ar, asmos_ar, current_moisture_inputs_ar)
        amov = forage.distribute_water_to_soil_layer(
            'amov')(adep_ar, afiel_ar, asmos_ar, current_moisture_inputs_ar)

        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            amov, known_modified_moisture_inputs - tolerance,
            known_modified_moisture_inputs + tolerance, _TARGET_NODATA)

    def test_calc_available_water_for_transpiration(self):
        """Test `calc_available_water_for_transpiration`.

        Use the function `calc_available_water_for_transpiration` to calculate
        water available in one soil layer for transpiration.

        Raises:
            AssertionError if `calc_available_water_for_transpiration` does not
            match values calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_size = (10, 10)
        tolerance = 0.0000001

        # low inputs, no water available for transpiration
        asmos = 3.6
        awilt = 0.52
        adep = 15
        known_avw = 0.

        asmos_ar = numpy.full(array_size, asmos)
        awilt_ar = numpy.full(array_size, awilt)
        adep_ar = numpy.full(array_size, adep)
        avw = forage.calc_available_water_for_transpiration(
            asmos_ar, awilt_ar, adep_ar)
        self.assert_all_values_in_array_within_range(
            avw, known_avw - tolerance, known_avw + tolerance, _TARGET_NODATA)

        # high moisture inputs, water available for transpiration
        asmos = 6.21
        awilt = 0.31
        adep = 15
        known_avw = 1.56

        asmos_ar = numpy.full(array_size, asmos)
        awilt_ar = numpy.full(array_size, awilt)
        adep_ar = numpy.full(array_size, adep)
        avw = forage.calc_available_water_for_transpiration(
            asmos_ar, awilt_ar, adep_ar)
        self.assert_all_values_in_array_within_range(
            avw, known_avw - tolerance, known_avw + tolerance, _TARGET_NODATA)

    def test_remove_transpiration(self):
        """ Test `remove_transpiration`.

        Use the function `remove_transpiration` to calculate asmos, revised
        moisture content of one soil layer, and avinj, water available for
        plant growth in the soil layer.

        Raises:
            AssertionError if `remove_transpiration` does not match value
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_size = (10, 10)
        tolerance = 0.00001

        # transpiration limited by current available moisture
        asmos = 4.15
        awilt = 0.26
        adep = 13.5
        trap = 4.17
        awwt = 1.428
        tot2 = 5.883

        known_asmos_revised = 3.51
        known_avinj = 0

        asmos_ar = numpy.full(array_size, asmos)
        awilt_ar = numpy.full(array_size, awilt)
        adep_ar = numpy.full(array_size, adep)
        trap_ar = numpy.full(array_size, trap)
        awwt_ar = numpy.full(array_size, awwt)
        tot2_ar = numpy.full(array_size, tot2)

        avinj = forage.remove_transpiration(
            'avinj')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        asmos_revised = forage.remove_transpiration(
            'asmos')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        self.assert_all_values_in_array_within_range(
            avinj, known_avinj - tolerance, known_avinj + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(asmos_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(awilt_ar, _TARGET_NODATA)

        avinj = forage.remove_transpiration(
            'avinj')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        asmos_revised = forage.remove_transpiration(
            'asmos')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        self.assert_all_values_in_array_within_range(
            avinj, known_avinj - tolerance, known_avinj + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)

        # transpiration limited by total potential transpiration
        asmos = 3.15
        awilt = 0.15
        adep = 12.5
        trap = 3.72
        awwt = 0.428
        tot2 = 4.883

        known_asmos_revised = 2.823938
        known_avinj = 0.948948

        asmos_ar = numpy.full(array_size, asmos)
        awilt_ar = numpy.full(array_size, awilt)
        adep_ar = numpy.full(array_size, adep)
        trap_ar = numpy.full(array_size, trap)
        awwt_ar = numpy.full(array_size, awwt)
        tot2_ar = numpy.full(array_size, tot2)

        avinj = forage.remove_transpiration(
            'avinj')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        asmos_revised = forage.remove_transpiration(
            'asmos')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        self.assert_all_values_in_array_within_range(
            avinj, known_avinj - tolerance, known_avinj + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(trap_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(adep_ar, _IC_NODATA)
        insert_nodata_values_into_array(tot2_ar, _TARGET_NODATA)

        avinj = forage.remove_transpiration(
            'avinj')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        asmos_revised = forage.remove_transpiration(
            'asmos')(asmos_ar, awilt_ar, adep_ar, trap_ar, awwt_ar, tot2_ar)
        self.assert_all_values_in_array_within_range(
            avinj, known_avinj - tolerance, known_avinj + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            asmos_revised, known_asmos_revised - tolerance,
            known_asmos_revised + tolerance, _TARGET_NODATA)

    def test_calc_relative_water_content_lyr_1(self):
        """Test `calc_relative_water_content_lyr_1`.

        Use the function `calc_relative_water_content_lyr_1` to calculate the
        relative water content of soil layer 1 prior to evaporative losses.

        Raises:
            AssertionError if `calc_relative_water_content_lyr_1` does not
                match values calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_size = (10, 10)
        tolerance = 0.00001

        asmos_1 = 2.52
        adep_1 = 16.42
        awilt_1 = 0.145
        afiel_1 = 0.774

        known_rwcf_1 = 0.013468

        asmos_1_ar = numpy.full(array_size, asmos_1)
        adep_1_ar = numpy.full(array_size, adep_1)
        awilt_1_ar = numpy.full(array_size, awilt_1)
        afiel_1_ar = numpy.full(array_size, afiel_1)

        rwcf_1 = forage.calc_relative_water_content_lyr_1(
            asmos_1_ar, adep_1_ar, awilt_1_ar, afiel_1_ar)
        self.assert_all_values_in_array_within_range(
            rwcf_1, known_rwcf_1 - tolerance, known_rwcf_1 + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(asmos_1_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(afiel_1_ar, _TARGET_NODATA)

        rwcf_1 = forage.calc_relative_water_content_lyr_1(
            asmos_1_ar, adep_1_ar, awilt_1_ar, afiel_1_ar)
        self.assert_all_values_in_array_within_range(
            rwcf_1, known_rwcf_1 - tolerance, known_rwcf_1 + tolerance,
            _TARGET_NODATA)

    def test_calc_evaporation_loss(self):
        """Test `calc_evaporation_loss`.

        Use the function `calc_evaporation_loss` to calculate moisture
        that evaporates from soil layer 1.

        Raises:
            AssertionError if `calc_evaporation_loss` does not match results
            calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_size = (10, 10)
        tolerance = 0.00001

        # limited by potential evaporation
        rwcf_1 = 0.99
        pevp = 3.1
        absevap = 2.1
        asmos_1 = 4.62
        awilt_1 = 0.153
        adep_1 = 14.2

        known_evlos = 0.64232

        rwcf_1_ar = numpy.full(array_size, rwcf_1)
        pevp_ar = numpy.full(array_size, pevp)
        absevap_ar = numpy.full(array_size, absevap)
        asmos_1_ar = numpy.full(array_size, asmos_1)
        awilt_1_ar = numpy.full(array_size, awilt_1)
        adep_1_ar = numpy.full(array_size, adep_1)

        evlos = forage.calc_evaporation_loss(
            rwcf_1_ar, pevp_ar, absevap_ar, asmos_1_ar, awilt_1_ar, adep_1_ar)
        self.assert_all_values_in_array_within_range(
            evlos, known_evlos - tolerance, known_evlos + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(rwcf_1_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(asmos_1_ar, _SV_NODATA)

        evlos = forage.calc_evaporation_loss(
            rwcf_1_ar, pevp_ar, absevap_ar, asmos_1_ar, awilt_1_ar, adep_1_ar)
        self.assert_all_values_in_array_within_range(
            evlos, known_evlos - tolerance, known_evlos + tolerance,
            _TARGET_NODATA)

        # limited by available moisture
        rwcf_1 = 0.99
        pevp = 8.2
        absevap = 2.1
        asmos_1 = 3.6
        awilt_1 = 0.153
        adep_1 = 14.2

        known_evlos = 1.4274

        rwcf_1_ar = numpy.full(array_size, rwcf_1)
        pevp_ar = numpy.full(array_size, pevp)
        absevap_ar = numpy.full(array_size, absevap)
        asmos_1_ar = numpy.full(array_size, asmos_1)
        awilt_1_ar = numpy.full(array_size, awilt_1)
        adep_1_ar = numpy.full(array_size, adep_1)

        evlos = forage.calc_evaporation_loss(
            rwcf_1_ar, pevp_ar, absevap_ar, asmos_1_ar, awilt_1_ar, adep_1_ar)
        self.assert_all_values_in_array_within_range(
            evlos, known_evlos - tolerance, known_evlos + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(pevp_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(adep_1_ar, _IC_NODATA)

        evlos = forage.calc_evaporation_loss(
            rwcf_1_ar, pevp_ar, absevap_ar, asmos_1_ar, awilt_1_ar, adep_1_ar)
        self.assert_all_values_in_array_within_range(
            evlos, known_evlos - tolerance, known_evlos + tolerance,
            _TARGET_NODATA)

    def test_raster_difference(self):
        """Test `raster_difference`.

        Use the function `raster_difference` to subtract one raster from
        another, while allowing nodata values in one raster to propagate to
        the result.  Then calculate the difference again, treating nodata
        values in the two rasters as zero.

        Raises:
            AssertionError if `raster_difference` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        raster1_val = 10
        raster2_val = 3
        known_result = 7
        raster1_path = os.path.join(self.workspace_dir, 'raster1.tif')
        raster2_path = os.path.join(self.workspace_dir, 'raster2.tif')
        target_path = os.path.join(self.workspace_dir, 'target.tif')
        create_random_raster(raster1_path, raster1_val, raster1_val)
        create_random_raster(raster2_path, raster2_val, raster2_val)

        raster1_nodata = -99
        raster2_nodata = -999

        forage.raster_difference(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=True)
        self.assert_all_values_in_raster_within_range(
            target_path, known_result, known_result, _TARGET_NODATA)

        # rasters contain nodata, which should be propagated to result
        insert_nodata_values_into_raster(raster1_path, raster1_nodata)
        insert_nodata_values_into_raster(raster2_path, raster2_nodata)
        forage.raster_difference(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=False)
        self.assert_all_values_in_raster_within_range(
            target_path, known_result, known_result, _TARGET_NODATA)

        # full raster of nodata, which should be treated as zero
        create_random_raster(raster1_path, raster1_val, raster1_val)
        create_random_raster(raster2_path, raster2_nodata, raster2_nodata)
        forage.raster_difference(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=True)
        self.assert_all_values_in_raster_within_range(
            target_path, raster1_val, raster1_val, _TARGET_NODATA)

    def test_raster_sum(self):
        """Test `raster_sum`.

        Use the function `raster_sum` to add two rasters, while allowing
        nodata values in one raster to propagate to the result.  Then
        calculate the difference again, treating nodata values as zero.

        Raises:
            AssertionError if `raster_sum` does not match values calculated by
                hand

        Returns:
            None

        """
        from rangeland_production import forage

        raster1_val = 10
        raster2_val = 3
        known_result = raster1_val + raster2_val
        raster1_path = os.path.join(self.workspace_dir, 'raster1.tif')
        raster2_path = os.path.join(self.workspace_dir, 'raster2.tif')
        target_path = os.path.join(self.workspace_dir, 'target.tif')
        create_random_raster(raster1_path, raster1_val, raster1_val)
        create_random_raster(raster2_path, raster2_val, raster2_val)

        raster1_nodata = -99
        raster2_nodata = -999

        forage.raster_sum(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=True)
        self.assert_all_values_in_raster_within_range(
            target_path, known_result, known_result, _TARGET_NODATA)

        # rasters contain nodata, which should be propagated to result
        insert_nodata_values_into_raster(raster1_path, raster1_nodata)
        insert_nodata_values_into_raster(raster2_path, raster2_nodata)
        forage.raster_sum(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=False)
        self.assert_all_values_in_raster_within_range(
            target_path, known_result, known_result, _TARGET_NODATA)

        # full raster of nodata, which should be treated as zero
        create_random_raster(raster1_path, raster1_val, raster1_val)
        create_random_raster(raster2_path, raster2_nodata, raster2_nodata)
        forage.raster_sum(
            raster1_path, raster1_nodata, raster2_path, raster2_nodata,
            target_path, _TARGET_NODATA, nodata_remove=True)
        self.assert_all_values_in_raster_within_range(
            target_path, raster1_val, raster1_val, _TARGET_NODATA)

    def test_soil_water(self):
        """Test `soil_water`.

        Use the function `soil_water` to distribute precipitation inputs to
        snow, evaporation from snow, surface evaporation, and transpiration
        by plants. Compare results to values calculated by a point-based
        version defined here.

        Raises:
            AssertionError if `_soil_water` does not match values calculated
                by point-based version

        Returns:
            None

        """
        def soil_water_point(
                precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
                shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
                pft_dict, adep, afiel, awilt, awtl):
            """Point-based implementation of `soil_water`.

            Parameters:
                precip (float): precipitation for this month, cm
                max_temp (float): maximum average temperature for this month,
                    deg C
                min_temp (float): minimum average temperature for this month,
                    deg C
                snow (float): existing snowpack before new snowfall for this
                    month
                snlq (float): existing liquid in snowpack before new snowfall
                pet (float): reference evapotranspiration
                tmelt_1 (float): parameter, minimum temperature above which
                    snow will melt
                tmelt_2 (float): parameter, ratio between degrees above
                    the minimum temperature and cm of snow that will melt
                shwave (float): shortwave radiation outside the atmosphere
                strucc_1 (float): carbon in surface structural litter
                metabc_1 (float): metabolic surface carbon
                fracro (float):  parameter, fraction of surface water
                    above precro that is lost to runoff
                precro (float):  parameter, amount of surface water that
                    must be available for runoff to occur
                fwloss_1 (float):  parameter, scaling factor for interception
                    and evaporation of precip by vegetation
                fwloss_2 (float):  parameter, scaling factor for bare soil
                    evaporation of precip
                pft_dict (dict): dictionary containing parameters and % cover
                    for plant functional types
                adep (float): parameter, depth of each soil layer in cm
                afiel (float): field capacity of each soil layer
                awilt (float): wilting point of each soil layer
                awtl (float): parameter, transpiration weighting factor for
                    each soil layer

            Returns:
                dictionary of values:
                    snow, current snowpack
                    snlq, current liquid in snow
                    amov_2, water moving from soil layer 2
                    asmos_<lyr>, current soil moisture, for lyr in 1:nlaypg_max
                    avh2o_1_<PFT>, water available for plant growth, for PFT
                        in pft_id_set
                    avh2o_3, available soil moisture in top two soil layers

            """
            # snow
            tave = (max_temp + min_temp) / 2.
            inputs_after_snow = precip
            if tave <= 0:
                snow = snow + precip
                inputs_after_snow = 0
            else:
                if snow > 0:
                    snlq = snlq + precip
                    inputs_after_snow = 0
            if snow > 0:
                snowtot = snow + snlq
                evsnow = min(snowtot, (pet * 0.87))
                snow = max(snow - evsnow * (snow/snowtot), 0.)
                snlq = max(snlq-evsnow * (snlq/snowtot), 0.)
                pet_rem = max((pet - evsnow / 0.87), 0)

                if tave >= tmelt_1:
                    snowmelt = tmelt_2 * (tave - tmelt_1) * shwave
                    snowmelt = max(snowmelt, 0)
                    snowmelt = min(snowmelt, snow)
                    snow = snow - snowmelt
                    snlq = snlq + snowmelt
                    if snlq > (0.5 * snow):
                        add = snlq - 0.5 * snow
                        snlq = snlq - add
                        inputs_after_snow = add
            else:
                pet_rem = pet

            # canopy and litter cover influencing surface losses
            sum_aglivc = sum(
                [pft_dict[pft_i]['aglivc'] * pft_dict[pft_i]['cover'] for
                    pft_i in pft_dict])
            sum_stdedc = sum(
                [pft_dict[pft_i]['stdedc'] * pft_dict[pft_i]['cover'] for
                    pft_i in pft_dict])
            sum_tgprod = sum(
                [pft_dict[pft_i]['tgprod'] * pft_dict[pft_i]['cover'] for
                    pft_i in pft_dict])
            alit = min((strucc_1 + metabc_1) * 2.5, 400)
            aliv = sum_aglivc * 2.5 + (0.25 * sum_tgprod)
            sd = min(aliv + (sum_stdedc * 2.5), 800.)
            # surface losses
            runoff = max(fracro * (inputs_after_snow - precro), 0.)
            inputs_after_surface = inputs_after_snow - runoff
            if snow == 0:
                aint = (0.0003 * alit + 0.0006 * sd) * fwloss_1
                absevap = (
                    0.5 * math.exp((-0.002 * alit) - (0.004 * sd)) * fwloss_2)
                evap_losses = min(
                    ((absevap + aint) * inputs_after_surface), 0.4 * pet_rem)
            else:
                absevap = 0
                evap_losses = 0
            inputs_after_surface = inputs_after_surface - evap_losses
            # potential transpiration
            current_moisture_inputs = inputs_after_surface
            trap = pet_rem - evap_losses
            if tave < 2:
                trap = 0
            else:
                trap = max(
                    min(trap, pet_rem * 0.65 *
                        (1 - math.exp(-0.02 * aliv))), 0)
            pevp = max(pet_rem - trap - evap_losses, 0.)
            tran = min(trap - 0.01, current_moisture_inputs)
            trap = trap - tran
            modified_moisture_inputs = current_moisture_inputs - tran
            # distribute moisture to soil layers prior to transpiration
            current_moisture_inputs = modified_moisture_inputs
            nlaypg_max = max(
                pft_dict[pft_i]['nlaypg'] for pft_i in pft_dict)
            asmos_dict = {lyr: asmos for lyr in range(1, nlaypg_max + 1)}
            amov_dict = {}
            for lyr in range(1, nlaypg_max + 1):
                afl = adep * afiel
                asmos_dict[lyr] = asmos_dict[lyr] + current_moisture_inputs
                if asmos_dict[lyr] > afl:
                    amov_dict[lyr] = asmos_dict[lyr]
                    asmos_dict[lyr] = afl
                else:
                    amov_dict[lyr] = 0
                current_moisture_inputs = amov_dict[lyr]
            # avw: available water for transpiration
            # awwt: water available for transpiration weighted by transpiration
            # depth for that soil layer
            awwt_dict = {}
            tot = 0
            tot2 = 0
            for lyr in range(1, nlaypg_max + 1):
                avw = max(asmos_dict[lyr] - awilt * adep, 0)
                awwt_dict[lyr] = avw * awtl
                tot = tot + avw
                tot2 = tot2 + awwt_dict[lyr]
            # revise total potential transpiration
            trap = min(trap, tot)
            # remove water via transpiration
            avinj_dict = {}
            for lyr in range(1, nlaypg_max + 1):
                avinj_dict[lyr] = max(asmos_dict[lyr] - awilt * adep, 0)
                trl = min((trap * awwt_dict[lyr]) / tot2, avinj_dict[lyr])
                avinj_dict[lyr] = avinj_dict[lyr] - trl
                asmos_dict[lyr] = asmos_dict[lyr] - trl
            # relative water content of soil layer 1
            rwcf_1 = (asmos_dict[1] / adep - awilt) / (afiel - awilt)
            # evaporation from soil layer 1
            evmt = max((rwcf_1 - 0.25) / (1 - 0.25), 0.01)
            evlos = min(
                evmt * pevp * absevap * 0.1,
                max(asmos_dict[1] - awilt * adep, 0))
            # remove evaporation from total moisture in soil layer 1
            asmos_dict[1] = asmos_dict[1] - evlos
            # remove evaporation from moisture available to plants in soil
            # layer 1
            avinj_dict[1] - avinj_dict[1] - evlos
            # calculate avh2o_1, soil water available for growth, for each PFT
            avh2o_1_dict = {}
            for pft_i in pft_dict:
                avh2o_1_dict[pft_i] = (
                    sum(avinj_dict[lyr] for lyr in
                        range(1, pft_dict[pft_i]['nlaypg'] + 1)) *
                    pft_dict[pft_i]['cover'])
            avh2o_3 = sum([avinj_dict[lyr] for lyr in [1, 2]])

            results_dict = {
                'snow': snow,
                'snlq': snlq,
                'amov_2': amov_dict[2],
                'avh2o_3': avh2o_3,
                'asmos': asmos_dict,
                'avh2o_1': avh2o_1_dict,
            }
            return results_dict

        def generate_model_inputs_from_point_inputs(
                precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
                shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
                pft_dict, adep, afiel, awilt, awtl):
            """Generate model inputs for `soil_water` from point inputs."""
            nrows = 1
            ncols = 1
            # aligned inputs
            aligned_inputs = {
                'max_temp_{}'.format(current_month): os.path.join(
                    self.workspace_dir,
                    'max_temp_{}.tif'.format(current_month)),
                'min_temp_{}'.format(current_month): os.path.join(
                    self.workspace_dir,
                    'min_temp_{}.tif'.format(current_month)),
                'precip_{}'.format(month_index): os.path.join(
                    self.workspace_dir, 'precip.tif'),
                'site_index': os.path.join(
                    self.workspace_dir, 'site_index.tif'),
            }
            create_random_raster(
                aligned_inputs['max_temp_{}'.format(current_month)], max_temp,
                max_temp, nrows=nrows, ncols=ncols)
            create_random_raster(
                aligned_inputs['min_temp_{}'.format(current_month)], min_temp,
                min_temp, nrows=nrows, ncols=ncols)
            create_random_raster(
                aligned_inputs['precip_{}'.format(month_index)], precip,
                precip, nrows=nrows, ncols=ncols)
            create_random_raster(
                aligned_inputs['site_index'], 1, 1, nrows=nrows, ncols=ncols)
            for pft_i in pft_dict:
                cover = pft_dict[pft_i]['cover']
                aligned_inputs['pft_{}'.format(pft_i)] = os.path.join(
                    self.workspace_dir, 'pft_{}.tif'.format(pft_i))
                create_random_raster(
                    aligned_inputs['pft_{}'.format(pft_i)], cover, cover,
                    nrows=nrows, ncols=ncols)

            # site param table
            site_param_table = {
                1: {
                    'tmelt_1': tmelt_1,
                    'tmelt_2': tmelt_2,
                    'fwloss_4': fwloss_4,
                    'fracro': fracro,
                    'precro': precro,
                    'fwloss_1': fwloss_1,
                    'fwloss_2': fwloss_2,
                    'nlayer': nlaypg_max,
                }
            }
            for lyr in range(1, nlaypg_max + 1):
                site_param_table[1]['adep_{}'.format(lyr)] = adep
                site_param_table[1]['awtl_{}'.format(lyr)] = awtl
            # veg trait table
            pft_id_set = set([i for i in pft_dict])
            veg_trait_table = {}
            for pft_i in pft_dict:
                veg_trait_table[pft_i] = {
                    'nlaypg': pft_dict[pft_i]['nlaypg'],
                    'growth_months': pft_dict[pft_i]['growth_months'],
                    'senescence_month': pft_dict[pft_i]['senescence_month'],
                }
            # previous state variables
            prev_sv_reg = {
                'strucc_1_path': os.path.join(
                    self.workspace_dir, 'strucc_1_prev.tif'),
                'metabc_1_path': os.path.join(
                    self.workspace_dir, 'metabc_1_prev.tif'),
                'snow_path': os.path.join(self.workspace_dir, 'snow_prev.tif'),
                'snlq_path': os.path.join(self.workspace_dir, 'snlq_prev.tif'),
            }
            create_random_raster(
                prev_sv_reg['strucc_1_path'], strucc_1, strucc_1, nrows=nrows,
                ncols=ncols)
            create_random_raster(
                prev_sv_reg['metabc_1_path'], metabc_1, metabc_1, nrows=nrows,
                ncols=ncols)
            create_random_raster(
                prev_sv_reg['snow_path'], snow, snow, nrows=nrows,
                ncols=ncols)
            create_random_raster(
                prev_sv_reg['snlq_path'], snlq, snlq, nrows=nrows,
                ncols=ncols)
            for lyr in range(1, nlaypg_max + 1):
                prev_sv_reg['asmos_{}_path'.format(lyr)] = os.path.join(
                    self.workspace_dir, 'asmos_{}_prev.tif'.format(lyr))
                create_random_raster(
                    prev_sv_reg['asmos_{}_path'.format(lyr)], asmos, asmos,
                    nrows=nrows, ncols=ncols)
            for pft_i in pft_dict:
                prev_sv_reg['aglivc_{}_path'.format(pft_i)] = os.path.join(
                    self.workspace_dir, 'aglivc_{}_prev.tif'.format(pft_i))
                prev_sv_reg['stdedc_{}_path'.format(pft_i)] = os.path.join(
                    self.workspace_dir, 'stdedc_{}_prev.tif'.format(pft_i))
                create_random_raster(
                    prev_sv_reg['aglivc_{}_path'.format(pft_i)],
                    pft_dict[pft_i]['aglivc'], pft_dict[pft_i]['aglivc'],
                    nrows=nrows, ncols=ncols)
                create_random_raster(
                    prev_sv_reg['stdedc_{}_path'.format(pft_i)],
                    pft_dict[pft_i]['stdedc'], pft_dict[pft_i]['stdedc'],
                    nrows=nrows, ncols=ncols)
            # current state variables
            sv_reg = {
                'snow_path': os.path.join(self.workspace_dir, 'snow.tif'),
                'snlq_path': os.path.join(self.workspace_dir, 'snlq.tif'),
                'avh2o_3_path': os.path.join(
                    self.workspace_dir, 'avh2o_3.tif'),
            }
            for lyr in range(1, nlaypg_max + 1):
                sv_reg['asmos_{}_path'.format(lyr)] = os.path.join(
                    self.workspace_dir, 'asmos_{}_path'.format(lyr))
            for pft_i in pft_dict:
                sv_reg['avh2o_1_{}_path'.format(pft_i)] = os.path.join(
                    self.workspace_dir, 'avh2o_1_{}.tif'.format(pft_i))
            # persistent parameters
            pp_reg = {}
            for lyr in range(1, nlaypg_max + 1):
                pp_reg['afiel_{}_path'.format(lyr)] = os.path.join(
                    self.workspace_dir, 'afiel_{}.tif'.format(lyr))
                pp_reg['awilt_{}_path'.format(lyr)] = os.path.join(
                    self.workspace_dir, 'awilt_{}.tif'.format(lyr))
                create_random_raster(
                    pp_reg['afiel_{}_path'.format(lyr)], afiel, afiel,
                    nrows=nrows, ncols=ncols)
                create_random_raster(
                    pp_reg['awilt_{}_path'.format(lyr)], awilt, awilt,
                    nrows=nrows, ncols=ncols)
            # monthly shared quantities
            month_reg = {
                'amov_1': os.path.join(self.workspace_dir, 'amov_1.tif'),
                'amov_2': os.path.join(self.workspace_dir, 'amov_2.tif'),
                'amov_3': os.path.join(self.workspace_dir, 'amov_3.tif'),
                'amov_4': os.path.join(self.workspace_dir, 'amov_4.tif'),
                'amov_5': os.path.join(self.workspace_dir, 'amov_5.tif'),
                'amov_6': os.path.join(self.workspace_dir, 'amov_6.tif'),
                'amov_7': os.path.join(self.workspace_dir, 'amov_7.tif'),
                'amov_8': os.path.join(self.workspace_dir, 'amov_8.tif'),
                'amov_9': os.path.join(self.workspace_dir, 'amov_9.tif'),
                'amov_10': os.path.join(self.workspace_dir, 'amov_10.tif'),
                'snowmelt': os.path.join(self.workspace_dir, 'snowmelt.tif')
            }
            for pft_i in pft_dict:
                month_reg['tgprod_{}'.format(pft_i)] = os.path.join(
                    self.workspace_dir, 'tgprod_{}.tif'.format(pft_i))
                create_random_raster(
                    month_reg['tgprod_{}'.format(pft_i)],
                    pft_dict[pft_i]['tgprod'], pft_dict[pft_i]['tgprod'],
                    nrows=nrows, ncols=ncols)
            input_dict = {
                'aligned_inputs': aligned_inputs,
                'site_param_table': site_param_table,
                'veg_trait_table': veg_trait_table,
                'current_month': current_month,
                'month_index': month_index,
                'prev_sv_reg': prev_sv_reg,
                'sv_reg': sv_reg,
                'pp_reg': pp_reg,
                'month_reg': month_reg,
                'pft_id_set': pft_id_set,
            }
            return input_dict
        from rangeland_production import forage

        # no snow, no snowfall
        pet = 4.9680004
        shwave = 457.95056

        # point inputs
        current_month = 10
        month_index = 9
        max_temp = 23.
        min_temp = -2.
        precip = 10.9

        # site parameters
        tmelt_1 = 0.
        tmelt_2 = 0.002
        fwloss_4 = 0.6
        fracro = 0.15
        precro = 8
        fwloss_1 = 0.8
        fwloss_2 = 0.779
        adep = 15
        awtl = 0.5

        # previous state variables
        strucc_1 = 46.1
        metabc_1 = 33.1
        snow = 0.
        snlq = 0.
        asmos = 2.04

        pft_dict = {
            1: {
                'cover': 0.4,
                'aglivc': 35.9,
                'stdedc': 49.874,
                'nlaypg': 5,
                'tgprod': 371.,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
            2: {
                'cover': 0.2,
                'aglivc': 52.1,
                'stdedc': 31.4,
                'nlaypg': 3,
                'tgprod': 300.2,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
            3: {
                'cover': 0.3,
                'aglivc': 20.77,
                'stdedc': 17.03,
                'nlaypg': 6,
                'tgprod': 200.8,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
        }
        nlaypg_max = max(
            pft_dict[pft_i]['nlaypg'] for pft_i in pft_dict)

        # persistent parameters
        afiel = 0.67
        awilt = 0.168

        tolerance = 0.000001
        results_dict = soil_water_point(
            precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
            shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
            pft_dict, adep, afiel, awilt, awtl)

        input_dict = generate_model_inputs_from_point_inputs(
            precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
            shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
            pft_dict, adep, afiel, awilt, awtl)
        forage._soil_water(
            input_dict['aligned_inputs'], input_dict['site_param_table'],
            input_dict['veg_trait_table'], input_dict['current_month'],
            input_dict['month_index'], input_dict['prev_sv_reg'],
            input_dict['pp_reg'], input_dict['pft_id_set'],
            input_dict['month_reg'], input_dict['sv_reg'])

        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['snow_path'],
            results_dict['snow'] - tolerance,
            results_dict['snow'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['snlq_path'],
            results_dict['snlq'] - tolerance,
            results_dict['snlq'] + tolerance, _SV_NODATA)
        for lyr in range(1, nlaypg_max + 1):
            self.assert_all_values_in_raster_within_range(
                input_dict['sv_reg']['asmos_{}_path'.format(lyr)],
                results_dict['asmos'][lyr] - tolerance,
                results_dict['asmos'][lyr] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['month_reg']['amov_2'],
            results_dict['amov_2'] - tolerance,
            results_dict['amov_2'] + tolerance, _TARGET_NODATA)
        for pft_i in input_dict['pft_id_set']:
            self.assert_all_values_in_raster_within_range(
                input_dict['sv_reg']['avh2o_1_{}_path'.format(pft_i)],
                results_dict['avh2o_1'][pft_i] - tolerance,
                results_dict['avh2o_1'][pft_i] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['avh2o_3_path'],
            results_dict['avh2o_3'] - tolerance,
            results_dict['avh2o_3'] + tolerance, _SV_NODATA)

        # large snowmelt, large precip
        pet = 4.9680004
        shwave = 457.95056

        # point inputs
        current_month = 10
        month_index = 9
        max_temp = 23.
        min_temp = -2.
        precip = 30.117

        # site parameters
        tmelt_1 = 0.
        tmelt_2 = 0.002
        fwloss_4 = 0.6
        fracro = 0.15
        precro = 8
        fwloss_1 = 0.8
        fwloss_2 = 0.779
        adep = 15
        awtl = 0.5

        # previous state variables
        strucc_1 = 46.1
        metabc_1 = 33.1
        snow = 7.2
        snlq = snow / 2.
        asmos = 0.882

        pft_dict = {
            1: {
                'cover': 0.4,
                'aglivc': 85.9,
                'stdedc': 49.874,
                'nlaypg': 5,
                'tgprod': 371.,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
            2: {
                'cover': 0.2,
                'aglivc': 12.1,
                'stdedc': 31.4,
                'nlaypg': 3,
                'tgprod': 300.2,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
            3: {
                'cover': 0.3,
                'aglivc': 27.77,
                'stdedc': 17.03,
                'nlaypg': 6,
                'tgprod': 200.8,
                'growth_months': ['9', '10', '11'],
                'senescence_month': 12,
            },
        }
        nlaypg_max = max(
            pft_dict[pft_i]['nlaypg'] for pft_i in pft_dict)

        # persistent parameters
        afiel = 0.67
        awilt = 0.168

        tolerance = 0.00001
        amov_tolerance = 0.011
        results_dict = soil_water_point(
            precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
            shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
            pft_dict, adep, afiel, awilt, awtl)

        input_dict = generate_model_inputs_from_point_inputs(
            precip, max_temp, min_temp, snow, snlq, pet, tmelt_1, tmelt_2,
            shwave, strucc_1, metabc_1, fracro, precro, fwloss_1, fwloss_2,
            pft_dict, adep, afiel, awilt, awtl)
        forage._soil_water(
            input_dict['aligned_inputs'], input_dict['site_param_table'],
            input_dict['veg_trait_table'], input_dict['current_month'],
            input_dict['month_index'], input_dict['prev_sv_reg'],
            input_dict['pp_reg'], input_dict['pft_id_set'],
            input_dict['month_reg'], input_dict['sv_reg'])

        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['snow_path'],
            results_dict['snow'] - tolerance,
            results_dict['snow'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['snlq_path'],
            results_dict['snlq'] - tolerance,
            results_dict['snlq'] + tolerance, _SV_NODATA)
        for lyr in range(1, nlaypg_max + 1):
            self.assert_all_values_in_raster_within_range(
                input_dict['sv_reg']['asmos_{}_path'.format(lyr)],
                results_dict['asmos'][lyr] - tolerance,
                results_dict['asmos'][lyr] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['month_reg']['amov_2'],
            results_dict['amov_2'] - amov_tolerance,
            results_dict['amov_2'] + amov_tolerance, _TARGET_NODATA)
        for pft_i in input_dict['pft_id_set']:
            self.assert_all_values_in_raster_within_range(
                input_dict['sv_reg']['avh2o_1_{}_path'.format(pft_i)],
                results_dict['avh2o_1'][pft_i] - tolerance,
                results_dict['avh2o_1'][pft_i] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            input_dict['sv_reg']['avh2o_3_path'],
            results_dict['avh2o_3'] - tolerance,
            results_dict['avh2o_3'] + tolerance, _SV_NODATA)

    def test_calc_anerb(self):
        """Test `calc_anerb`.

        Use the function `calc_anerb` to calculate the effect of soil anaerobic
        conditions on decomposition. Compare the calculated value to a value
        calculated by point-based version.

        Raises:
            AssertionError if anerb does not match value calculated by
                point-based version

        Returns:
            None

        """

        from rangeland_production import forage

        array_shape = (10, 10)
        tolerance = 0.00000001

        # low rprpet, anerb = 1
        rprpet = 0.8824
        pevap = 6.061683
        drain = 0.003
        aneref_1 = 1.5
        aneref_2 = 3.
        aneref_3 = 0.3

        rprpet_arr = numpy.full(array_shape, rprpet)
        pevap_arr = numpy.full(array_shape, pevap)
        drain_arr = numpy.full(array_shape, drain)
        aneref_1_arr = numpy.full(array_shape, aneref_1)
        aneref_2_arr = numpy.full(array_shape, aneref_2)
        aneref_3_arr = numpy.full(array_shape, aneref_3)

        anerb = calc_anerb_point(
            rprpet, pevap, drain, aneref_1, aneref_2, aneref_3)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(rprpet_arr, _TARGET_NODATA)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

        # high rprpet, xh2o > 0
        rprpet = 2.0004
        rprpet_arr = numpy.full(array_shape, rprpet)
        anerb = calc_anerb_point(
            rprpet, pevap, drain, aneref_1, aneref_2, aneref_3)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(drain_arr, _IC_NODATA)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

        # high rprpet, xh2o = 0
        drain = 1.
        drain_arr = numpy.full(array_shape, drain)
        anerb = calc_anerb_point(
            rprpet, pevap, drain, aneref_1, aneref_2, aneref_3)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(pevap_arr, _TARGET_NODATA)
        anerb_arr = forage.calc_anerb(
            rprpet_arr, pevap_arr, drain_arr, aneref_1_arr, aneref_2_arr,
            aneref_3_arr)
        self.assert_all_values_in_array_within_range(
            anerb_arr, anerb - tolerance, anerb + tolerance, _TARGET_NODATA)

    def test_declig_point(self):
        """Test `declig_point`.

        Use the function `declig_point` to calculate change in state variables
        as material containing lignin decomposes into SOM2 and SOM1. Compare
        calculated changes in state variables to changes calculated by hand.

        Raises:
            AssertionError if `declig_point` does not match values calculated
                by hand

        Returns:
            None

        """
        # no decomposition happens, mineral ratios are insufficient
        aminrl_1 = 0.
        aminrl_2 = 0.
        ligcon = 0.3779
        rsplig = 0.0146
        ps1co2_lyr = 0.0883
        strucc_lyr = 155.5253
        tcflow = 40.82
        struce_lyr_1 = 0.7776
        struce_lyr_2 = 0.3111
        rnew_lyr_1_1 = 190.  # observed ratio: 200.0068
        rnew_lyr_2_1 = 300.  # observed ratio: 499.9206
        rnew_lyr_1_2 = 0.
        rnew_lyr_2_2 = 0.
        minerl_1_1 = 0.
        minerl_1_2 = 0.

        d_strucc_lyr = declig_point(
            'd_strucc')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_struce_lyr_1 = declig_point(
            'd_struce_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_struce_lyr_2 = declig_point(
            'd_struce_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_minerl_1_1 = declig_point(
            'd_minerl_1_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_minerl_1_2 = declig_point(
            'd_minerl_1_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_gromin_1 = declig_point(
            'd_gromin_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2c_lyr = declig_point(
            'd_som2c')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2e_lyr_1 = declig_point(
            'd_som2e_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2e_lyr_2 = declig_point(
            'd_som2e_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1c_lyr = declig_point(
            'd_som1c')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1e_lyr_1 = declig_point(
            'd_som1e_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1e_lyr_2 = declig_point(
            'd_som1e_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)

        self.assertEqual(d_strucc_lyr, 0)
        self.assertEqual(d_struce_lyr_1, 0)
        self.assertEqual(d_struce_lyr_2, 0)
        self.assertEqual(d_minerl_1_1, 0)
        self.assertEqual(d_minerl_1_2, 0)
        self.assertEqual(d_gromin_1, 0)
        self.assertEqual(d_som2c_lyr, 0)
        self.assertEqual(d_som2e_lyr_1, 0)
        self.assertEqual(d_som2e_lyr_2, 0)
        self.assertEqual(d_som1c_lyr, 0)
        self.assertEqual(d_som1e_lyr_1, 0)
        self.assertEqual(d_som1e_lyr_2, 0)

        # decomposition occurs, subsidized by mineral N and P
        aminrl_1 = 6.4944
        aminrl_2 = 33.2791
        ligcon = 0.3779
        rsplig = 0.0146
        ps1co2_lyr = 0.0883
        strucc_lyr = 155.5253
        tcflow = 40.82
        struce_lyr_1 = 0.7776
        struce_lyr_2 = 0.3111
        rnew_lyr_1_1 = 210.8  # greater than observed ratio: 200.0068
        rnew_lyr_2_1 = 540.2  # greater than observed ratio: 499.9206
        rnew_lyr_1_2 = 190.3
        rnew_lyr_2_2 = 520.8
        minerl_1_1 = 6.01
        minerl_1_2 = 32.87

        # values calculated by hand
        d_strucc_lyr_obs = -40.82
        d_struce_lyr_1_obs = -0.204093044668617
        d_struce_lyr_2_obs = -0.08165296578756
        d_minerl_1_1_obs = 0.014387319170996
        d_minerl_1_2_obs = 0.00960796090459662
        d_gromin_1_obs = 0.0182639608121622
        d_som2c_lyr_obs = 15.2006601812
        d_som2e_lyr_1_obs = 0.0798773525023647
        d_som2e_lyr_2_obs = 0.029187135524578
        d_som1c_lyr_obs = 23.1518210274
        d_som1e_lyr_1_obs = 0.109828372995256
        d_som1e_lyr_2_obs = 0.0428578693583858

        # call 12 times, 12 return values
        d_strucc_lyr = declig_point(
            'd_strucc')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_struce_lyr_1 = declig_point(
            'd_struce_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_struce_lyr_2 = declig_point(
            'd_struce_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_minerl_1_1 = declig_point(
            'd_minerl_1_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_minerl_1_2 = declig_point(
            'd_minerl_1_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_gromin_1 = declig_point(
            'd_gromin_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2c_lyr = declig_point(
            'd_som2c')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2e_lyr_1 = declig_point(
            'd_som2e_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som2e_lyr_2 = declig_point(
            'd_som2e_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1c_lyr = declig_point(
            'd_som1c')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1e_lyr_1 = declig_point(
            'd_som1e_1')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)
        d_som1e_lyr_2 = declig_point(
            'd_som1e_2')(
                aminrl_1, aminrl_2, ligcon, rsplig, ps1co2_lyr, strucc_lyr,
                tcflow, struce_lyr_1, struce_lyr_2, rnew_lyr_1_1, rnew_lyr_2_1,
                rnew_lyr_1_2, rnew_lyr_2_2, minerl_1_1, minerl_1_2)

        self.assertAlmostEqual(d_strucc_lyr, d_strucc_lyr_obs, places=10)
        self.assertAlmostEqual(d_struce_lyr_1, d_struce_lyr_1_obs, places=10)
        self.assertAlmostEqual(d_struce_lyr_2, d_struce_lyr_2_obs, places=10)
        self.assertAlmostEqual(d_minerl_1_1, d_minerl_1_1_obs, places=10)
        self.assertAlmostEqual(d_minerl_1_2, d_minerl_1_2_obs, places=10)
        self.assertAlmostEqual(d_gromin_1, d_gromin_1_obs, places=10)
        self.assertAlmostEqual(d_som2c_lyr, d_som2c_lyr_obs, places=10)
        self.assertAlmostEqual(d_som2e_lyr_1, d_som2e_lyr_1_obs, places=10)
        self.assertAlmostEqual(d_som2e_lyr_2, d_som2e_lyr_2_obs, places=10)
        self.assertAlmostEqual(d_som1c_lyr, d_som1c_lyr_obs, places=10)
        self.assertAlmostEqual(d_som1e_lyr_1, d_som1e_lyr_1_obs, places=10)
        self.assertAlmostEqual(d_som1e_lyr_2, d_som1e_lyr_2_obs, places=10)

    def test_esched(self):
        """Test `esched`.

        Use the function `esched` to calculate the flow of one element
        accompanying decomposition of C.  Test that the function matches
        values calculated by point-based version.

        Raises:
            AssertionError if `esched` does not match value calculated
                by `esched_point`

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00000001

        # immobilization
        cflow = 15.2006
        tca = 155.5253
        rcetob = 190.3
        anps = 0.7776
        labile = 6.01

        material_leaving_a = esched_point(
            'material_leaving_a')(cflow, tca, rcetob, anps, labile)
        material_arriving_b = esched_point(
            'material_arriving_b')(cflow, tca, rcetob, anps, labile)
        mineral_flow = esched_point(
            'mineral_flow')(cflow, tca, rcetob, anps, labile)

        # raster inputs
        cflow_path = os.path.join(self.workspace_dir, 'cflow.tif')
        tca_path = os.path.join(self.workspace_dir, 'tca.tif')
        rcetob_path = os.path.join(self.workspace_dir, 'rcetob.tif')
        anps_path = os.path.join(self.workspace_dir, 'anps.tif')
        labile_path = os.path.join(self.workspace_dir, 'labile.tif')
        # output paths
        mat_leaving_a_path = os.path.join(self.workspace_dir, 'leavinga.tif')
        mat_arriving_b_path = os.path.join(self.workspace_dir, 'arrivingb.tif')
        mineral_flow_path = os.path.join(self.workspace_dir, 'mineralflow.tif')

        create_random_raster(cflow_path, cflow, cflow)
        create_random_raster(tca_path, tca, tca)
        create_random_raster(rcetob_path, rcetob, rcetob)
        create_random_raster(anps_path, anps, anps)
        create_random_raster(labile_path, labile, labile)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        insert_nodata_values_into_raster(cflow_path, _IC_NODATA)
        insert_nodata_values_into_raster(anps_path, _SV_NODATA)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        # mineralization
        cflow = 15.2006
        tca = 155.5253
        rcetob = 520.8
        anps = 0.3111
        labile = 32.87

        material_leaving_a = esched_point(
            'material_leaving_a')(cflow, tca, rcetob, anps, labile)
        material_arriving_b = esched_point(
            'material_arriving_b')(cflow, tca, rcetob, anps, labile)
        mineral_flow = esched_point(
            'mineral_flow')(cflow, tca, rcetob, anps, labile)

        create_random_raster(cflow_path, cflow, cflow)
        create_random_raster(tca_path, tca, tca)
        create_random_raster(rcetob_path, rcetob, rcetob)
        create_random_raster(anps_path, anps, anps)
        create_random_raster(labile_path, labile, labile)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        insert_nodata_values_into_raster(anps_path, _SV_NODATA)
        insert_nodata_values_into_raster(tca_path, _SV_NODATA)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        # no movement
        cflow = 15.2006
        tca = 155.5253
        rcetob = 520.8
        anps = 0.3111
        labile = 0.

        material_leaving_a = esched_point(
            'material_leaving_a')(cflow, tca, rcetob, anps, labile)
        material_arriving_b = esched_point(
            'material_arriving_b')(cflow, tca, rcetob, anps, labile)
        mineral_flow = esched_point(
            'mineral_flow')(cflow, tca, rcetob, anps, labile)

        create_random_raster(cflow_path, cflow, cflow)
        create_random_raster(tca_path, tca, tca)
        create_random_raster(rcetob_path, rcetob, rcetob)
        create_random_raster(anps_path, anps, anps)
        create_random_raster(labile_path, labile, labile)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        insert_nodata_values_into_raster(rcetob_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(labile_path, _SV_NODATA)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_leaving_a'), mat_leaving_a_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('material_arriving_b'), mat_arriving_b_path,
            gdal.GDT_Float32, _IC_NODATA)
        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                cflow_path, tca_path, rcetob_path, anps_path, labile_path]],
            forage.esched('mineral_flow'), mineral_flow_path,
            gdal.GDT_Float32, _IC_NODATA)

        self.assert_all_values_in_raster_within_range(
            mat_leaving_a_path, material_leaving_a - tolerance,
            material_leaving_a + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mat_arriving_b_path, material_arriving_b - tolerance,
            material_arriving_b + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            mineral_flow_path, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

    def test_nutrient_flow(self):
        """Test `nutrient_flow`.

        Use the function `nutrient_flow` to calculate and apply the flow of
        one element accompanying decomposition of C. Test calculated values
        against values calculated by point-based version.

        Raises:
            AssertionError if `nutrient_flow` does not match values calculated
                by `esched_point`

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00000001

        # immobilization
        cflow = 15.2006
        tca = 155.5253
        rcetob = 190.3
        anps = 0.7776
        labile = 6.01

        material_leaving_a = esched_point(
            'material_leaving_a')(cflow, tca, rcetob, anps, labile)
        material_arriving_b = esched_point(
            'material_arriving_b')(cflow, tca, rcetob, anps, labile)
        mineral_flow = esched_point(
            'mineral_flow')(cflow, tca, rcetob, anps, labile)

        d_estatv_donating = -material_leaving_a
        d_estatv_receiving = material_arriving_b
        d_minerl = mineral_flow
        if mineral_flow > 0:
            gromin = mineral_flow
        else:
            gromin = 0

        # raster inputs
        cflow_path = os.path.join(self.workspace_dir, 'cflow.tif')
        tca_path = os.path.join(self.workspace_dir, 'tca.tif')
        rcetob_path = os.path.join(self.workspace_dir, 'rcetob.tif')
        anps_path = os.path.join(self.workspace_dir, 'anps.tif')
        labile_path = os.path.join(self.workspace_dir, 'labile.tif')
        d_estatv_donating_path = os.path.join(
            self.workspace_dir, 'estatv_donating.tif')
        d_estatv_receiving_path = os.path.join(
            self.workspace_dir, 'estatv_receiving.tif')
        d_minerl_path = os.path.join(self.workspace_dir, 'minerl.tif')
        gromin_path = os.path.join(self.workspace_dir, 'gromin.tif')

        create_random_raster(cflow_path, cflow, cflow)
        create_random_raster(tca_path, tca, tca)
        create_random_raster(rcetob_path, rcetob, rcetob)
        create_random_raster(anps_path, anps, anps)
        create_random_raster(labile_path, labile, labile)
        create_random_raster(d_estatv_donating_path, 0, 0)
        create_random_raster(d_estatv_receiving_path, 0, 0)
        create_random_raster(d_minerl_path, 0, 0)
        create_random_raster(gromin_path, 0, 0)

        forage.nutrient_flow(
            cflow_path, tca_path, anps_path, rcetob_path,
            labile_path, d_estatv_donating_path, d_estatv_receiving_path,
            d_minerl_path, gromin_path)
        self.assert_all_values_in_raster_within_range(
            d_estatv_donating_path, d_estatv_donating - tolerance,
            d_estatv_donating + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_estatv_receiving_path, d_estatv_receiving - tolerance,
            d_estatv_receiving + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_minerl_path, d_minerl - tolerance, d_minerl + tolerance,
            _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            gromin_path, gromin - tolerance, gromin + tolerance, _IC_NODATA)

        create_random_raster(d_estatv_donating_path, 0, 0)
        create_random_raster(d_estatv_receiving_path, 0, 0)
        create_random_raster(d_minerl_path, 0, 0)
        create_random_raster(gromin_path, 0, 0)

        insert_nodata_values_into_raster(cflow_path, _IC_NODATA)
        insert_nodata_values_into_raster(tca_path, _SV_NODATA)
        insert_nodata_values_into_raster(rcetob_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(anps_path, _SV_NODATA)
        insert_nodata_values_into_raster(d_estatv_donating_path, _IC_NODATA)

        forage.nutrient_flow(
            cflow_path, tca_path, anps_path, rcetob_path,
            labile_path, d_estatv_donating_path, d_estatv_receiving_path,
            d_minerl_path, gromin_path)
        self.assert_all_values_in_raster_within_range(
            d_estatv_donating_path, d_estatv_donating - tolerance,
            d_estatv_donating + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_estatv_receiving_path, d_estatv_receiving - tolerance,
            d_estatv_receiving + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_minerl_path, d_minerl - tolerance, d_minerl + tolerance,
            _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            gromin_path, gromin - tolerance, gromin + tolerance,
            _TARGET_NODATA)

        # mineralization
        cflow = 15.2006
        tca = 155.5253
        rcetob = 520.8
        anps = 0.3111
        labile = 32.87

        material_leaving_a = esched_point(
            'material_leaving_a')(cflow, tca, rcetob, anps, labile)
        material_arriving_b = esched_point(
            'material_arriving_b')(cflow, tca, rcetob, anps, labile)
        mineral_flow = esched_point(
            'mineral_flow')(cflow, tca, rcetob, anps, labile)

        d_estatv_donating = -material_leaving_a
        d_estatv_receiving = material_arriving_b
        d_minerl = mineral_flow

        # raster inputs
        create_random_raster(cflow_path, cflow, cflow)
        create_random_raster(tca_path, tca, tca)
        create_random_raster(rcetob_path, rcetob, rcetob)
        create_random_raster(anps_path, anps, anps)
        create_random_raster(labile_path, labile, labile)
        create_random_raster(d_estatv_donating_path, 0, 0)
        create_random_raster(d_estatv_receiving_path, 0, 0)
        create_random_raster(d_minerl_path, 0, 0)

        forage.nutrient_flow(
            cflow_path, tca_path, anps_path, rcetob_path,
            labile_path, d_estatv_donating_path, d_estatv_receiving_path,
            d_minerl_path)
        self.assert_all_values_in_raster_within_range(
            d_estatv_donating_path, d_estatv_donating - tolerance,
            d_estatv_donating + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_estatv_receiving_path, d_estatv_receiving - tolerance,
            d_estatv_receiving + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_minerl_path, d_minerl - tolerance, d_minerl + tolerance,
            _IC_NODATA)

        create_random_raster(d_estatv_donating_path, 0, 0)
        create_random_raster(d_estatv_receiving_path, 0, 0)
        create_random_raster(d_minerl_path, 0, 0)

        insert_nodata_values_into_raster(cflow_path, _IC_NODATA)
        insert_nodata_values_into_raster(tca_path, _SV_NODATA)
        insert_nodata_values_into_raster(rcetob_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(anps_path, _SV_NODATA)
        insert_nodata_values_into_raster(d_estatv_donating_path, _IC_NODATA)

        forage.nutrient_flow(
            cflow_path, tca_path, anps_path, rcetob_path,
            labile_path, d_estatv_donating_path, d_estatv_receiving_path,
            d_minerl_path)
        self.assert_all_values_in_raster_within_range(
            d_estatv_donating_path, d_estatv_donating - tolerance,
            d_estatv_donating + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_estatv_receiving_path, d_estatv_receiving - tolerance,
            d_estatv_receiving + tolerance, _IC_NODATA)
        self.assert_all_values_in_raster_within_range(
            d_minerl_path, d_minerl - tolerance, d_minerl + tolerance,
            _IC_NODATA)

    def test_fsfunc(self):
        """Test `fsfunc`.

        Use the function `fsfunc` to calculate the fraction of mineral P that
        is in solution.  Compare calculated value to value calculated by point
        version.

        Raises:
            AssertionError if `initialize_aminrl_2` does not match value
                calculated by point version of function

        Returns:
            None

        """
        from rangeland_production import forage

        tolerance = 0.00001

        # known values
        minerl_1_2 = 32.87
        sorpmx = 2.
        pslsrb = 1.
        fsol_point = fsfunc_point(minerl_1_2, pslsrb, sorpmx)

        # raster inputs
        minerl_1_2_path = os.path.join(self.workspace_dir, 'minerl_1_2.tif')
        sorpmx_path = os.path.join(self.workspace_dir, 'sorpmx.tif')
        pslsrb_path = os.path.join(self.workspace_dir, 'pslsrb.tif')
        fsol_path = os.path.join(self.workspace_dir, 'fsol.tif')

        create_random_raster(minerl_1_2_path, minerl_1_2, minerl_1_2)
        create_random_raster(sorpmx_path, sorpmx, sorpmx)
        create_random_raster(pslsrb_path, pslsrb, pslsrb)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                minerl_1_2_path, sorpmx_path, pslsrb_path]],
            forage.fsfunc, fsol_path, gdal.GDT_Float32,
            _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            fsol_path, fsol_point - tolerance, fsol_point + tolerance,
            _SV_NODATA)

        insert_nodata_values_into_raster(minerl_1_2_path, _SV_NODATA)
        insert_nodata_values_into_raster(pslsrb_path, _IC_NODATA)

        pygeoprocessing.raster_calculator(
            [(path, 1) for path in [
                minerl_1_2_path, sorpmx_path, pslsrb_path]],
            forage.fsfunc, fsol_path, gdal.GDT_Float32,
            _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            fsol_path, fsol_point - tolerance, fsol_point + tolerance,
            _SV_NODATA)

    def test_calc_tcflow_strucc_1(self):
        """Test `calc_tcflow_strucc_1`.

        Use the function `calc_tcflow_strucc_1` to calculate total flow
        out of surface structural C. Ensure that calculated values match
        values calculated by point-based version defined here.

        Raises:
            AssertionError if `calc_tcflow_strucc_1` does not match values
                calculated by point-based version

        Returns:
            None

        """
        def tcflow_strucc_1_point(
                aminrl_1, aminrl_2, strucc_1, struce_1_1, struce_1_2,
                rnewas_1_1, rnewas_2_1, strmax_1, defac, dec1_1, pligst_1,
                strlig_1, pheff_struc):
            """Point-based implementation of `calc_tcflow_strucc_1`.

            Returns:
                tcflow_strucc_1, total flow of C limited by N and P
            """
            potential_flow = (min(
                strucc_1, strmax_1) * defac * dec1_1 *
                math.exp(-pligst_1 * strlig_1) * 0.020833 * pheff_struc)

            decompose_mask = (
                ((aminrl_1 > 0.0000001) | (
                    (strucc_1 / struce_1_1) <= rnewas_1_1)) &
                ((aminrl_2 > 0.0000001) | (
                    (strucc_1 / struce_1_2) <= rnewas_2_1)))

            if decompose_mask:
                tcflow_strucc_1 = potential_flow
            else:
                tcflow_strucc_1 = 0
            return tcflow_strucc_1
        from rangeland_production import forage

        array_shape = (10, 10)
        tolerance = 0.0000001

        # decomposition can occur
        aminrl_1 = 6.4143
        aminrl_2 = 30.9253
        strucc_1 = 156.0546
        struce_1_1 = 0.7803
        struce_1_2 = 0.3121
        rnewas_1_1 = 210.8
        rnewas_2_1 = 540.2
        strmax_1 = 5000.
        defac = 0.822
        dec1_1 = 3.9
        pligst_1 = 3.
        strlig_1 = 0.3779
        pH = 6.84
        pheff_struc = numpy.clip(
            (0.5 + (1.1 / numpy.pi) *
                numpy.arctan(numpy.pi * 0.7 * (pH - 4.))), 0, 1)

        tcflow_strucc_1 = tcflow_strucc_1_point(
            aminrl_1, aminrl_2, strucc_1, struce_1_1, struce_1_2,
            rnewas_1_1, rnewas_2_1, strmax_1, defac, dec1_1, pligst_1,
            strlig_1, pheff_struc)

        # array inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        strucc_1_ar = numpy.full(array_shape, strucc_1)
        struce_1_1_ar = numpy.full(array_shape, struce_1_1)
        struce_1_2_ar = numpy.full(array_shape, struce_1_2)
        rnewas_1_1_ar = numpy.full(array_shape, rnewas_1_1)
        rnewas_2_1_ar = numpy.full(array_shape, rnewas_2_1)
        strmax_1_ar = numpy.full(array_shape, strmax_1)
        defac_ar = numpy.full(array_shape, defac)
        dec1_1_ar = numpy.full(array_shape, dec1_1)
        pligst_1_ar = numpy.full(array_shape, pligst_1)
        strlig_1_ar = numpy.full(array_shape, strlig_1)
        pheff_struc_ar = numpy.full(array_shape, pheff_struc)

        tcflow_strucc1_ar = forage.calc_tcflow_strucc_1(
            aminrl_1_ar, aminrl_2_ar, strucc_1_ar, struce_1_1_ar,
            struce_1_2_ar, rnewas_1_1_ar, rnewas_2_1_ar, strmax_1_ar, defac_ar,
            dec1_1_ar, pligst_1_ar, strlig_1_ar, pheff_struc_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_strucc1_ar, tcflow_strucc_1 - tolerance,
            tcflow_strucc_1 + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(struce_1_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(defac_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(strlig_1_ar, _SV_NODATA)

        tcflow_strucc1_ar = forage.calc_tcflow_strucc_1(
            aminrl_1_ar, aminrl_2_ar, strucc_1_ar, struce_1_1_ar,
            struce_1_2_ar, rnewas_1_1_ar, rnewas_2_1_ar, strmax_1_ar, defac_ar,
            dec1_1_ar, pligst_1_ar, strlig_1_ar, pheff_struc_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_strucc1_ar, tcflow_strucc_1 - tolerance,
            tcflow_strucc_1 + tolerance, _IC_NODATA)

        # N insufficient to allow decomposition
        aminrl_1 = 0.
        aminrl_2 = 30.9253
        strucc_1 = 156.0546
        struce_1_1 = 0.7803
        struce_1_2 = 0.3121
        rnewas_1_1 = 170.
        rnewas_2_1 = 540.2
        strmax_1 = 5000.
        defac = 0.822
        dec1_1 = 3.9
        pligst_1 = 3.
        strlig_1 = 0.3779
        pH = 6.84
        pheff_struc = numpy.clip(
            (0.5 + (1.1 / numpy.pi) *
                numpy.arctan(numpy.pi * 0.7 * (pH - 4.))), 0, 1)

        tcflow_strucc_1 = tcflow_strucc_1_point(
            aminrl_1, aminrl_2, strucc_1, struce_1_1, struce_1_2,
            rnewas_1_1, rnewas_2_1, strmax_1, defac, dec1_1, pligst_1,
            strlig_1, pheff_struc)

        # array inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        strucc_1_ar = numpy.full(array_shape, strucc_1)
        struce_1_1_ar = numpy.full(array_shape, struce_1_1)
        struce_1_2_ar = numpy.full(array_shape, struce_1_2)
        rnewas_1_1_ar = numpy.full(array_shape, rnewas_1_1)
        rnewas_2_1_ar = numpy.full(array_shape, rnewas_2_1)
        strmax_1_ar = numpy.full(array_shape, strmax_1)
        defac_ar = numpy.full(array_shape, defac)
        dec1_1_ar = numpy.full(array_shape, dec1_1)
        pligst_1_ar = numpy.full(array_shape, pligst_1)
        strlig_1_ar = numpy.full(array_shape, strlig_1)
        pheff_struc_ar = numpy.full(array_shape, pheff_struc)

        tcflow_strucc1_ar = forage.calc_tcflow_strucc_1(
            aminrl_1_ar, aminrl_2_ar, strucc_1_ar, struce_1_1_ar,
            struce_1_2_ar, rnewas_1_1_ar, rnewas_2_1_ar, strmax_1_ar, defac_ar,
            dec1_1_ar, pligst_1_ar, strlig_1_ar, pheff_struc_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_strucc1_ar, tcflow_strucc_1 - tolerance,
            tcflow_strucc_1 + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(strmax_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(dec1_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(aminrl_1_ar, _SV_NODATA)

        tcflow_strucc1_ar = forage.calc_tcflow_strucc_1(
            aminrl_1_ar, aminrl_2_ar, strucc_1_ar, struce_1_1_ar,
            struce_1_2_ar, rnewas_1_1_ar, rnewas_2_1_ar, strmax_1_ar, defac_ar,
            dec1_1_ar, pligst_1_ar, strlig_1_ar, pheff_struc_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_strucc1_ar, tcflow_strucc_1 - tolerance,
            tcflow_strucc_1 + tolerance, _IC_NODATA)

    def test_reclassify_nodata(self):
        """Test `reclassify_nodata`.

        Use the function `reclassify_nodata` to reset the nodata value of
        a raster.

        Raises:
            AssertionError if the nodata value of a raster following
                `reclassify_nodata` is not equal to the specified nodata type
            AssertionError if unique values in a raster contain more than the
                fill value and the correct nodata value

        Returns:
            None

        """
        from rangeland_production import forage

        fill_value = 0
        target_path = os.path.join(self.workspace_dir, 'target_raster.tif')
        create_random_raster(target_path, fill_value, fill_value)
        insert_nodata_values_into_raster(target_path, _TARGET_NODATA)

        new_nodata_value = -999
        forage.reclassify_nodata(target_path, new_nodata_value)
        result_nodata_value = pygeoprocessing.get_raster_info(
            target_path)['nodata'][0]
        self.assertEqual(
            new_nodata_value, result_nodata_value,
            msg="New nodata value does not match specified nodata value")

        # check unique values inside raster
        raster_values = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (target_path, 1)):
            raster_values.update(numpy.unique(raster_block))
        self.assertEqual(
            raster_values, set([fill_value, float(new_nodata_value)]),
            msg="Raster contains extraneous values")

        new_nodata_value = float(numpy.finfo('float32').min)
        forage.reclassify_nodata(target_path, new_nodata_value)
        result_nodata_value = pygeoprocessing.get_raster_info(
            target_path)['nodata'][0]
        self.assertEqual(
            new_nodata_value, result_nodata_value,
            msg="New nodata value does not match specified nodata value")
        raster_values = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (target_path, 1)):
            raster_values.update(numpy.unique(raster_block))
        self.assertEqual(
            raster_values, set([fill_value, float(new_nodata_value)]),
            msg="Raster contains extraneous values")

        new_nodata_value = 8920
        forage.reclassify_nodata(target_path, new_nodata_value)
        insert_nodata_values_into_raster(target_path, new_nodata_value)
        result_nodata_value = pygeoprocessing.get_raster_info(
            target_path)['nodata'][0]
        self.assertEqual(
            new_nodata_value, result_nodata_value,
            msg="New nodata value does not match specified nodata value")
        raster_values = set()
        for offset_map, raster_block in pygeoprocessing.iterblocks(
                (target_path, 1)):
            raster_values.update(numpy.unique(raster_block))
        self.assertEqual(
            raster_values, set([fill_value, float(new_nodata_value)]),
            msg="Raster contains extraneous values")

    def test_calc_respiration_mineral_flow(self):
        """Test `calc_respiration_mineral_flow`.

        Use the function `calc_respiration_mineral_flow` to calculate
        mineral flow of one element associated with respiration. Compare
        the result to values calculated by point-based verison defined
        here.

        Raises:
            AssertionError if `calc_respiration_mineral_flow` does not
                match values calculated by point-based version

        Returns:
            None

        """
        def respir_minr_flow_point(cflow, frac_co2, estatv, cstatv):
            co2_loss = cflow * frac_co2
            mineral_flow = co2_loss * estatv / cstatv
            return mineral_flow

        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.0000000001

        # known values
        cflow = 15.2006601
        frac_co2 = 0.0146
        estatv = 0.7776
        cstatv = 155.5253
        mineral_flow = respir_minr_flow_point(cflow, frac_co2, estatv, cstatv)

        cflow_ar = numpy.full(array_shape, cflow)
        frac_co2_ar = numpy.full(array_shape, frac_co2)
        estatv_ar = numpy.full(array_shape, estatv)
        cstatv_ar = numpy.full(array_shape, cstatv)
        mineral_flow_ar = forage.calc_respiration_mineral_flow(
            cflow_ar, frac_co2_ar, estatv_ar, cstatv_ar)

        self.assert_all_values_in_array_within_range(
            mineral_flow_ar, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(cflow_ar, _IC_NODATA)
        insert_nodata_values_into_array(frac_co2_ar, _IC_NODATA)
        insert_nodata_values_into_array(estatv_ar, _SV_NODATA)
        insert_nodata_values_into_array(cstatv_ar, _SV_NODATA)

        mineral_flow_ar = forage.calc_respiration_mineral_flow(
            cflow_ar, frac_co2_ar, estatv_ar, cstatv_ar)

        self.assert_all_values_in_array_within_range(
            mineral_flow_ar, mineral_flow - tolerance,
            mineral_flow + tolerance, _IC_NODATA)

    def test_update_gross_mineralization(self):
        """Test `update_gross_mineralization`.

        Test the function `update_gross_mineralization`  against values
        calculated by hand.

        Raises:
            AssertionError if `update_gross_mineralization` does not match
                values calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.0000001

        # known values
        gross_mineralization = 0.0481
        mineral_flow = 0.00044
        gromin_updated = gross_mineralization + mineral_flow

        gross_mineralization_ar = numpy.full(array_shape, gross_mineralization)
        mineral_flow_ar = numpy.full(array_shape, mineral_flow)

        gromin_updated_ar = forage.update_gross_mineralization(
            gross_mineralization_ar, mineral_flow_ar)
        self.assert_all_values_in_array_within_range(
            gromin_updated_ar, gromin_updated - tolerance,
            gromin_updated + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(
            gross_mineralization_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(mineral_flow_ar, _IC_NODATA)

        gromin_updated_ar = forage.update_gross_mineralization(
            gross_mineralization_ar, mineral_flow_ar)
        self.assert_all_values_in_array_within_range(
            gromin_updated_ar, gromin_updated - tolerance,
            gromin_updated + tolerance, _TARGET_NODATA)

        # known values
        gross_mineralization = 0.048881
        mineral_flow = -0.00674
        gromin_updated = gross_mineralization

        gross_mineralization_ar = numpy.full(array_shape, gross_mineralization)
        mineral_flow_ar = numpy.full(array_shape, mineral_flow)

        gromin_updated_ar = forage.update_gross_mineralization(
            gross_mineralization_ar, mineral_flow_ar)
        self.assert_all_values_in_array_within_range(
            gromin_updated_ar, gromin_updated - tolerance,
            gromin_updated + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(
            gross_mineralization_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(mineral_flow_ar, _IC_NODATA)

        gromin_updated_ar = forage.update_gross_mineralization(
            gross_mineralization_ar, mineral_flow_ar)
        self.assert_all_values_in_array_within_range(
            gromin_updated_ar, gromin_updated - tolerance,
            gromin_updated + tolerance, _TARGET_NODATA)

    def test_calc_net_cflow(self):
        """Test `calc_net_cflow`.

        Test `calc_net_cflow` against value calculated by hand.

        Raises:
            AssertionError if `calc_net_cflow` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.0000001

        # known values
        cflow = 5.2006601
        frac_co2 = 0.0182
        net_cflow = cflow - (cflow * frac_co2)

        cflow_ar = numpy.full(array_shape, cflow)
        frac_co2_ar = numpy.full(array_shape, frac_co2)
        net_cflow_ar = forage.calc_net_cflow(cflow_ar, frac_co2_ar)

        self.assert_all_values_in_array_within_range(
            net_cflow_ar, net_cflow - tolerance, net_cflow + tolerance,
            _IC_NODATA)

        insert_nodata_values_into_array(cflow_ar, _IC_NODATA)
        insert_nodata_values_into_array(frac_co2_ar, _IC_NODATA)

        net_cflow_ar = forage.calc_net_cflow(cflow_ar, frac_co2_ar)

        self.assert_all_values_in_array_within_range(
            net_cflow_ar, net_cflow - tolerance, net_cflow + tolerance,
            _IC_NODATA)

    def test_calc_tcflow_surface(self):
        """Test `calc_tcflow_surface`.

        Test `calc_tcflow_surface` against value calculated by point-based
        version.

        Raises:
            AssertionError if `calc_tcflow_surface` does not match value
                calculated by point-based version

        Returns:
            None

        """
        def calc_tcflow_surface_point(
                aminrl_1, aminrl_2, metabc_1, metabe_1_1, metabe_1_2,
                rceto1_1, rceto1_2, defac, dec2_1, pheff_metab):
            """Point implementation of `calc_tcflow_surface`."""
            decompose_mask = (
                ((aminrl_1 > 0.0000001) | (
                    (metabc_1 / metabe_1_1) <= rceto1_1)) &
                ((aminrl_2 > 0.0000001) | (
                    (metabc_1 / metabe_1_2) <= rceto1_2)))  # line 194 Litdec.f
            if decompose_mask:
                tcflow_metabc_1 = numpy.clip(
                    (metabc_1 * defac * dec2_1 * 0.020833 * pheff_metab), 0,
                    metabc_1)
            else:
                tcflow_metabc_1 = 0.
            return tcflow_metabc_1
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.00001

        # known values, decomposition can occur
        aminrl_1 = 5.8821
        aminrl_2 = 0.04781
        metabc_1 = 169.22
        metabe_1_1 = 0.7776
        metabe_1_2 = 0.3111
        rceto1_1 = 5.29
        rceto1_2 = 2.92
        defac = 0.822
        dec2_1 = 3.9
        pheff_metab = 0.9917

        tcflow_metabc_1_point = calc_tcflow_surface_point(
            aminrl_1, aminrl_2, metabc_1, metabe_1_1, metabe_1_2,
            rceto1_1, rceto1_2, defac, dec2_1, pheff_metab)

        # raster inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        metabc_1_ar = numpy.full(array_shape, metabc_1)
        metabe_1_1_ar = numpy.full(array_shape, metabe_1_1)
        metabe_1_2_ar = numpy.full(array_shape, metabe_1_2)
        rceto1_1_ar = numpy.full(array_shape, rceto1_1)
        rceto1_2_ar = numpy.full(array_shape, rceto1_2)
        defac_ar = numpy.full(array_shape, defac)
        dec2_1_ar = numpy.full(array_shape, dec2_1)
        pheff_metab_ar = numpy.full(array_shape, pheff_metab)

        tcflow_metabc_1_ar = forage.calc_tcflow_surface(
            aminrl_1_ar, aminrl_2_ar, metabc_1_ar, metabe_1_1_ar,
            metabe_1_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_1_ar,
            pheff_metab_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_metabc_1_ar, tcflow_metabc_1_point - tolerance,
            tcflow_metabc_1_point + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(aminrl_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(defac_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(metabe_1_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(metabe_1_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(metabc_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(pheff_metab_ar, _TARGET_NODATA)

        tcflow_metabc_1_ar = forage.calc_tcflow_surface(
            aminrl_1_ar, aminrl_2_ar, metabc_1_ar, metabe_1_1_ar,
            metabe_1_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_1_ar,
            pheff_metab_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_metabc_1_ar, tcflow_metabc_1_point - tolerance,
            tcflow_metabc_1_point + tolerance, _IC_NODATA)

        # known values, no decomposition
        aminrl_1 = 0.
        aminrl_2 = 0.
        metabc_1 = 169.22
        metabe_1_1 = 0.7776
        metabe_1_2 = 0.3111
        rceto1_1 = 200.
        rceto1_2 = 400.
        defac = 0.822
        dec2_1 = 3.9
        pheff_metab = 0.9917

        tcflow_metabc_1_point = calc_tcflow_surface_point(
            aminrl_1, aminrl_2, metabc_1, metabe_1_1, metabe_1_2,
            rceto1_1, rceto1_2, defac, dec2_1, pheff_metab)

        # raster inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        metabc_1_ar = numpy.full(array_shape, metabc_1)
        metabe_1_1_ar = numpy.full(array_shape, metabe_1_1)
        metabe_1_2_ar = numpy.full(array_shape, metabe_1_2)
        rceto1_1_ar = numpy.full(array_shape, rceto1_1)
        rceto1_2_ar = numpy.full(array_shape, rceto1_2)
        defac_ar = numpy.full(array_shape, defac)
        dec2_1_ar = numpy.full(array_shape, dec2_1)
        pheff_metab_ar = numpy.full(array_shape, pheff_metab)

        tcflow_metabc_1_ar = forage.calc_tcflow_surface(
            aminrl_1_ar, aminrl_2_ar, metabc_1_ar, metabe_1_1_ar,
            metabe_1_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_1_ar,
            pheff_metab_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_metabc_1_ar, tcflow_metabc_1_point - tolerance,
            tcflow_metabc_1_point + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(aminrl_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(defac_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(rceto1_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(metabe_1_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(dec2_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(pheff_metab_ar, _TARGET_NODATA)

        tcflow_metabc_1_ar = forage.calc_tcflow_surface(
            aminrl_1_ar, aminrl_2_ar, metabc_1_ar, metabe_1_1_ar,
            metabe_1_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_1_ar,
            pheff_metab_ar)

        self.assert_all_values_in_array_within_range(
            tcflow_metabc_1_ar, tcflow_metabc_1_point - tolerance,
            tcflow_metabc_1_point + tolerance, _IC_NODATA)

    def test_calc_tcflow_soil(self):
        """Test `calc_tcflow_soil`.

        Test `calc_tcflow_soil` against value calculated by point-based
        version.

        Raises:
            AssertionError if `calc_tcflow_soil` does not match value
                calculated by point-based version

        Returns:
            None

        """
        def calc_tcflow_soil_point(
                aminrl_1, aminrl_2, metabc_2, metabe_2_1, metabe_2_2, rceto1_1,
                rceto1_2, defac, dec2_2, pheff_metab, anerb):
            """Point implementation of `calc_tcflow_soil`."""
            decompose_mask = (
                ((aminrl_1 > 0.0000001) | (
                    (metabc_2 / metabe_2_1) <= rceto1_1)) &
                ((aminrl_2 > 0.0000001) | (
                    (metabc_2 / metabe_2_2) <= rceto1_2)))  # line 194 Litdec.f
            if decompose_mask:
                tcflow_metabc_2 = numpy.clip(
                    (metabc_2 * defac * dec2_2 * 0.020833 * pheff_metab *
                        anerb), 0, metabc_2)
            else:
                tcflow_metabc_2 = 0.
            return tcflow_metabc_2
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.00001

        # known values, decomposition can occur
        aminrl_1 = 5.8821
        aminrl_2 = 0.04781
        metabc_2 = 169.22
        metabe_2_1 = 0.7776
        metabe_2_2 = 0.3111
        rceto1_1 = 5.29
        rceto1_2 = 2.92
        defac = 0.822
        dec2_2 = 3.9
        pheff_metab = 0.9917
        anerb = 0.3

        tcflow_metabc_2_point = calc_tcflow_soil_point(
            aminrl_1, aminrl_2, metabc_2, metabe_2_1, metabe_2_2,
            rceto1_1, rceto1_2, defac, dec2_2, pheff_metab, anerb)

        # raster inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        metabc_2_ar = numpy.full(array_shape, metabc_2)
        metabe_2_1_ar = numpy.full(array_shape, metabe_2_1)
        metabe_2_2_ar = numpy.full(array_shape, metabe_2_2)
        rceto1_1_ar = numpy.full(array_shape, rceto1_1)
        rceto1_2_ar = numpy.full(array_shape, rceto1_2)
        defac_ar = numpy.full(array_shape, defac)
        dec2_2_ar = numpy.full(array_shape, dec2_2)
        pheff_metab_ar = numpy.full(array_shape, pheff_metab)
        anerb_ar = numpy.full(array_shape, anerb)

        tcflow_metabc_2_ar = forage.calc_tcflow_soil(
            aminrl_1_ar, aminrl_2_ar, metabc_2_ar, metabe_2_1_ar,
            metabe_2_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_2_ar,
            pheff_metab_ar, anerb_ar)
        self.assert_all_values_in_array_within_range(
            tcflow_metabc_2_ar, tcflow_metabc_2_point - tolerance,
            tcflow_metabc_2_point + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(aminrl_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(defac_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(metabe_2_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(metabe_2_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(anerb_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(metabc_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(pheff_metab_ar, _TARGET_NODATA)

        tcflow_metabc_2_ar = forage.calc_tcflow_soil(
            aminrl_1_ar, aminrl_2_ar, metabc_2_ar, metabe_2_1_ar,
            metabe_2_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_2_ar,
            pheff_metab_ar, anerb_ar)
        self.assert_all_values_in_array_within_range(
            tcflow_metabc_2_ar, tcflow_metabc_2_point - tolerance,
            tcflow_metabc_2_point + tolerance, _IC_NODATA)

        # known values, no decomposition
        aminrl_1 = 0.
        aminrl_2 = 0.
        metabc_2 = 169.22
        metabe_2_1 = 0.7776
        metabe_2_2 = 0.3111
        rceto1_1 = 200.
        rceto1_2 = 400.
        defac = 0.822
        dec2_2 = 3.9
        pheff_metab = 0.9917

        tcflow_metabc_2_point = calc_tcflow_soil_point(
            aminrl_1, aminrl_2, metabc_2, metabe_2_1, metabe_2_2,
            rceto1_1, rceto1_2, defac, dec2_2, pheff_metab, anerb)

        # raster inputs
        aminrl_1_ar = numpy.full(array_shape, aminrl_1)
        aminrl_2_ar = numpy.full(array_shape, aminrl_2)
        metabc_2_ar = numpy.full(array_shape, metabc_2)
        metabe_2_1_ar = numpy.full(array_shape, metabe_2_1)
        metabe_2_2_ar = numpy.full(array_shape, metabe_2_2)
        rceto1_1_ar = numpy.full(array_shape, rceto1_1)
        rceto1_2_ar = numpy.full(array_shape, rceto1_2)
        defac_ar = numpy.full(array_shape, defac)
        dec2_2_ar = numpy.full(array_shape, dec2_2)
        pheff_metab_ar = numpy.full(array_shape, pheff_metab)
        anerb_ar = numpy.full(array_shape, anerb)

        tcflow_metabc_2_ar = forage.calc_tcflow_soil(
            aminrl_1_ar, aminrl_2_ar, metabc_2_ar, metabe_2_1_ar,
            metabe_2_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_2_ar,
            pheff_metab_ar, anerb_ar)
        self.assert_all_values_in_array_within_range(
            tcflow_metabc_2_ar, tcflow_metabc_2_point - tolerance,
            tcflow_metabc_2_point + tolerance, _IC_NODATA)

        insert_nodata_values_into_array(aminrl_2_ar, _SV_NODATA)
        insert_nodata_values_into_array(defac_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(rceto1_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(metabe_2_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(dec2_2_ar, _IC_NODATA)
        insert_nodata_values_into_array(pheff_metab_ar, _TARGET_NODATA)

        tcflow_metabc_2_ar = forage.calc_tcflow_soil(
            aminrl_1_ar, aminrl_2_ar, metabc_2_ar, metabe_2_1_ar,
            metabe_2_2_ar, rceto1_1_ar, rceto1_2_ar, defac_ar, dec2_2_ar,
            pheff_metab_ar, anerb_ar)
        self.assert_all_values_in_array_within_range(
            tcflow_metabc_2_ar, tcflow_metabc_2_point - tolerance,
            tcflow_metabc_2_point + tolerance, _IC_NODATA)

    def test_belowground_ratio(self):
        """Test `_belowground_ratio`.

        Use the function `_belowground_ratio` to calculate required C/iel
        ratio of belowground decomposing material.  Compare calculate values
        to values calculated by point-based version.

        Raises:
            AssertionError if `_belowground_ratio` does not match values
                calculated by point-based version

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.00001

        # known values, aminrl > varat_3_iel
        aminrl = 5.928
        varat_1_iel = 14.
        varat_2_iel = 3.
        varat_3_iel = 2.

        belowground_point = bgdrat_point(
            aminrl, varat_1_iel, varat_2_iel, varat_3_iel)

        # array inputs
        aminrl_ar = numpy.full(array_shape, aminrl)
        varat_1_iel_ar = numpy.full(array_shape, varat_1_iel)
        varat_2_iel_ar = numpy.full(array_shape, varat_2_iel)
        varat_3_iel_ar = numpy.full(array_shape, varat_3_iel)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(aminrl_ar, _SV_NODATA)
        insert_nodata_values_into_array(varat_1_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_2_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_3_iel_ar, _IC_NODATA)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

        # no mineral source
        aminrl = 0.
        varat_1_iel = 14.
        varat_2_iel = 3.
        varat_3_iel = 2.

        belowground_point = bgdrat_point(
            aminrl, varat_1_iel, varat_2_iel, varat_3_iel)

        # array inputs
        aminrl_ar = numpy.full(array_shape, aminrl)
        varat_1_iel_ar = numpy.full(array_shape, varat_1_iel)
        varat_2_iel_ar = numpy.full(array_shape, varat_2_iel)
        varat_3_iel_ar = numpy.full(array_shape, varat_3_iel)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(aminrl_ar, _SV_NODATA)
        insert_nodata_values_into_array(varat_1_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_2_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_3_iel_ar, _IC_NODATA)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

        # known values, aminrl < varat_3_iel
        aminrl = 1.9917
        varat_1_iel = 14.
        varat_2_iel = 5.
        varat_3_iel = 3.

        belowground_point = bgdrat_point(
            aminrl, varat_1_iel, varat_2_iel, varat_3_iel)

        # array inputs
        aminrl_ar = numpy.full(array_shape, aminrl)
        varat_1_iel_ar = numpy.full(array_shape, varat_1_iel)
        varat_2_iel_ar = numpy.full(array_shape, varat_2_iel)
        varat_3_iel_ar = numpy.full(array_shape, varat_3_iel)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(aminrl_ar, _SV_NODATA)
        insert_nodata_values_into_array(varat_1_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_2_iel_ar, _IC_NODATA)
        insert_nodata_values_into_array(varat_3_iel_ar, _IC_NODATA)

        belowground_ratio = forage._belowground_ratio(
            aminrl_ar, varat_1_iel_ar, varat_2_iel_ar, varat_3_iel_ar)
        self.assert_all_values_in_array_within_range(
            belowground_ratio, belowground_point - tolerance,
            belowground_point + tolerance, _TARGET_NODATA)

    def test_calc_surface_som2_ratio(self):
        """Test `calc_surface_som2_ratio`.

        Use the function `calc_surface_som2_ratio` to calculate the required
        ratio for material entering surface SOM2. Compare the calculated
        value to value calculated by hand.

        Raises:
            AssertionError if `calc_surface_som2_ratio` does not match value
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.00001

        # known values, calc term > rad1p_3
        som1c_1 = 12.8192
        som1e_1 = 1.5752
        rad1p_1 = 12.
        rad1p_2 = 3.
        rad1p_3 = 5.
        pcemic1_2 = 10.
        rceto2_surface = 14.552565

        # array inputs
        som1c_1_ar = numpy.full(array_shape, som1c_1)
        som1e_1_ar = numpy.full(array_shape, som1e_1)
        rad1p_1_ar = numpy.full(array_shape, rad1p_1)
        rad1p_2_ar = numpy.full(array_shape, rad1p_2)
        rad1p_3_ar = numpy.full(array_shape, rad1p_3)
        pcemic1_2_ar = numpy.full(array_shape, pcemic1_2)

        receto2_surface_ar = forage.calc_surface_som2_ratio(
            som1c_1_ar,  som1e_1_ar, rad1p_1_ar, rad1p_2_ar, rad1p_3_ar,
            pcemic1_2_ar)
        self.assert_all_values_in_array_within_range(
            receto2_surface_ar, rceto2_surface - tolerance,
            rceto2_surface + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(som1c_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(som1e_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(rad1p_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(rad1p_2_ar, _IC_NODATA)
        insert_nodata_values_into_array(rad1p_3_ar, _IC_NODATA)
        insert_nodata_values_into_array(pcemic1_2_ar, _IC_NODATA)

        receto2_surface_ar = forage.calc_surface_som2_ratio(
            som1c_1_ar,  som1e_1_ar, rad1p_1_ar, rad1p_2_ar, rad1p_3_ar,
            pcemic1_2_ar)
        self.assert_all_values_in_array_within_range(
            receto2_surface_ar, rceto2_surface - tolerance,
            rceto2_surface + tolerance, _TARGET_NODATA)

        # known values, calc term < rad1p_3
        som1c_1 = 12.8192
        som1e_1 = 2.
        rad1p_1 = 8.
        rad1p_2 = 3.
        rad1p_3 = 5.
        pcemic1_2 = 10.
        rceto2_surface = 5.

        # array inputs
        som1c_1_ar = numpy.full(array_shape, som1c_1)
        som1e_1_ar = numpy.full(array_shape, som1e_1)
        rad1p_1_ar = numpy.full(array_shape, rad1p_1)
        rad1p_2_ar = numpy.full(array_shape, rad1p_2)
        rad1p_3_ar = numpy.full(array_shape, rad1p_3)
        pcemic1_2_ar = numpy.full(array_shape, pcemic1_2)

        receto2_surface_ar = forage.calc_surface_som2_ratio(
            som1c_1_ar,  som1e_1_ar, rad1p_1_ar, rad1p_2_ar, rad1p_3_ar,
            pcemic1_2_ar)
        self.assert_all_values_in_array_within_range(
            receto2_surface_ar, rceto2_surface - tolerance,
            rceto2_surface + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(som1c_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(som1e_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(rad1p_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(rad1p_2_ar, _IC_NODATA)
        insert_nodata_values_into_array(rad1p_3_ar, _IC_NODATA)
        insert_nodata_values_into_array(pcemic1_2_ar, _IC_NODATA)

        receto2_surface_ar = forage.calc_surface_som2_ratio(
            som1c_1_ar,  som1e_1_ar, rad1p_1_ar, rad1p_2_ar, rad1p_3_ar,
            pcemic1_2_ar)
        self.assert_all_values_in_array_within_range(
            receto2_surface_ar, rceto2_surface - tolerance,
            rceto2_surface + tolerance, _TARGET_NODATA)

    def test_calc_c_leach(self):
        """Test `calc_c_leach`.

        Use the function `calc_c_leach` to calculate the C leaching
        from soil SOM1 into stream flow during decomposition.  Compare
        calculated values to value calculated by hand.

        Raises:
            AssertionError if `calc_c_leach` does not match value
                calculated by hand.

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (10, 10)
        tolerance = 0.00001

        # known values, linten > 1
        amov_2 = 63.1
        tcflow = 40.38
        omlech_3 = 60.
        orglch = 0.07
        cleach = 2.8266

        # array inputs
        amov_2_ar = numpy.full(array_shape, amov_2)
        tcflow_ar = numpy.full(array_shape, tcflow)
        omlech_3_ar = numpy.full(array_shape, omlech_3)
        orglch_ar = numpy.full(array_shape, orglch)

        cleach_ar = forage.calc_c_leach(
            amov_2_ar, tcflow_ar, omlech_3_ar, orglch_ar)
        self.assert_all_values_in_array_within_range(
            cleach_ar, cleach - tolerance, cleach + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(amov_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(tcflow_ar, _IC_NODATA)
        insert_nodata_values_into_array(omlech_3_ar, _IC_NODATA)
        insert_nodata_values_into_array(orglch_ar, _IC_NODATA)

        cleach_ar = forage.calc_c_leach(
            amov_2_ar, tcflow_ar, omlech_3_ar, orglch_ar)
        self.assert_all_values_in_array_within_range(
            cleach_ar, cleach - tolerance, cleach + tolerance, _TARGET_NODATA)

        # known values, linten < 1
        amov_2 = 10.5
        tcflow = 40.38
        omlech_3 = 60.
        orglch = 0.07
        cleach = 0.494655

        # array inputs
        amov_2_ar = numpy.full(array_shape, amov_2)
        tcflow_ar = numpy.full(array_shape, tcflow)
        omlech_3_ar = numpy.full(array_shape, omlech_3)
        orglch_ar = numpy.full(array_shape, orglch)

        cleach_ar = forage.calc_c_leach(
            amov_2_ar, tcflow_ar, omlech_3_ar, orglch_ar)
        self.assert_all_values_in_array_within_range(
            cleach_ar, cleach - tolerance, cleach + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(amov_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(tcflow_ar, _IC_NODATA)
        insert_nodata_values_into_array(omlech_3_ar, _IC_NODATA)
        insert_nodata_values_into_array(orglch_ar, _IC_NODATA)

        cleach_ar = forage.calc_c_leach(
            amov_2_ar, tcflow_ar, omlech_3_ar, orglch_ar)
        self.assert_all_values_in_array_within_range(
            cleach_ar, cleach - tolerance, cleach + tolerance, _TARGET_NODATA)

    def test_remove_leached_iel(self):
        """Test `remove_leached_iel`.

        Use the function `remove_leached_iel` to remove leached nutrients from
        SOM1 during decomposition. Test the calculated values against values
        calculated by hand.

        Raises:
            AssertionError if calculated values do not match values calculated
                by hand

        """
        from rangeland_production import forage
        nrows = 10
        ncols = 10
        tolerance = 0.00001

        # known values, leaching N
        som1c_2 = 10.5
        som1e_2_iel = 40.38
        cleach = 0.494655
        iel = 1
        d_som1e_2_iel_before = 50.22
        d_som1e_2_iel_after = 49.2688491

        # raster inputs
        som1c_2_path = os.path.join(self.workspace_dir, 'som1c_2.tif')
        som1e_2_iel_path = os.path.join(self.workspace_dir, 'som1e_2_iel.tif')
        cleach_path = os.path.join(self.workspace_dir, 'cleach.tif')
        d_som1e_2_iel_path = os.path.join(
            self.workspace_dir, 'd_som1e_2_iel.tif')
        create_random_raster(som1c_2_path, som1c_2, som1c_2)
        create_random_raster(som1e_2_iel_path, som1e_2_iel, som1e_2_iel)
        create_random_raster(cleach_path, cleach, cleach)
        create_random_raster(
            d_som1e_2_iel_path, d_som1e_2_iel_before, d_som1e_2_iel_before)

        forage.remove_leached_iel(
            som1c_2_path, som1e_2_iel_path, cleach_path, d_som1e_2_iel_path,
            iel)
        self.assert_all_values_in_raster_within_range(
            d_som1e_2_iel_path, d_som1e_2_iel_after - tolerance,
            d_som1e_2_iel_after + tolerance, _IC_NODATA)

        create_random_raster(
            d_som1e_2_iel_path, d_som1e_2_iel_before, d_som1e_2_iel_before)
        insert_nodata_values_into_raster(som1c_2_path, _SV_NODATA)
        insert_nodata_values_into_raster(som1e_2_iel_path, _SV_NODATA)
        insert_nodata_values_into_raster(cleach_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(d_som1e_2_iel_path, _IC_NODATA)

        forage.remove_leached_iel(
            som1c_2_path, som1e_2_iel_path, cleach_path, d_som1e_2_iel_path,
            iel)
        self.assert_all_values_in_raster_within_range(
            d_som1e_2_iel_path, d_som1e_2_iel_after - tolerance,
            d_som1e_2_iel_after + tolerance, _IC_NODATA)

        # known values, leaching P
        som1c_2 = 10.5
        som1e_2_iel = 40.38
        cleach = 0.494655
        iel = 2
        d_som1e_2_iel_before = 50.22
        d_som1e_2_iel_after = 50.16564852

        # raster inputs
        som1c_2_path = os.path.join(self.workspace_dir, 'som1c_2.tif')
        som1e_2_iel_path = os.path.join(self.workspace_dir, 'som1e_2_iel.tif')
        cleach_path = os.path.join(self.workspace_dir, 'cleach.tif')
        d_som1e_2_iel_path = os.path.join(
            self.workspace_dir, 'd_som1e_2_iel.tif')
        create_random_raster(som1c_2_path, som1c_2, som1c_2)
        create_random_raster(som1e_2_iel_path, som1e_2_iel, som1e_2_iel)
        create_random_raster(cleach_path, cleach, cleach)
        create_random_raster(
            d_som1e_2_iel_path, d_som1e_2_iel_before, d_som1e_2_iel_before)

        forage.remove_leached_iel(
            som1c_2_path, som1e_2_iel_path, cleach_path, d_som1e_2_iel_path,
            iel)
        self.assert_all_values_in_raster_within_range(
            d_som1e_2_iel_path, d_som1e_2_iel_after - tolerance,
            d_som1e_2_iel_after + tolerance, _IC_NODATA)

        create_random_raster(
            d_som1e_2_iel_path, d_som1e_2_iel_before, d_som1e_2_iel_before)
        insert_nodata_values_into_raster(som1c_2_path, _SV_NODATA)
        insert_nodata_values_into_raster(som1e_2_iel_path, _SV_NODATA)
        insert_nodata_values_into_raster(cleach_path, _TARGET_NODATA)
        insert_nodata_values_into_raster(d_som1e_2_iel_path, _IC_NODATA)

        forage.remove_leached_iel(
            som1c_2_path, som1e_2_iel_path, cleach_path, d_som1e_2_iel_path,
            iel)
        self.assert_all_values_in_raster_within_range(
            d_som1e_2_iel_path, d_som1e_2_iel_after - tolerance,
            d_som1e_2_iel_after + tolerance, _IC_NODATA)

    def test_partit(self):
        """Test `partit`.

        Use the function `partit` to partition organic residue into structural
        and metabolic material.  Test the calculated quantities against values
        calculated by point-based version defined here.

        Raises:
            AssertionError if the change in C, N, P, and lignin calculated by
                `partit` does not match the value calculated by point-based
                version

        Returns:
            None

        """
        def partit_point(
                cpart, epart_1, epart_2, damr_lyr_1, damr_lyr_2, minerl_1_1,
                minerl_1_2, damrmn_1, damrmn_2, pabres, frlign, spl_1, spl_2,
                rcestr_1, rcestr_2, strlig_lyr, strucc_lyr, metabc_lyr,
                struce_lyr_1, metabe_lyr_1, struce_lyr_2, metabe_lyr_2):
            """Partition incoming material into structural and metabolic.

            When organic material is added to the soil, for example as dead
            biomass falls and becomes litter, or when organic material is added
            from animal waste, it must be partitioned into structural
            (STRUCC_lyr) and metabolic (METABC_lyr) material.  This is done
            according to the ratio of lignin to N in the residue.

            Parameters:
                cpart (float): C in incoming material
                epart_1 (float): N in incoming material
                epart_2 (float): P in incoming material
                damr_lyr_1 (float): parameter, fraction of N in lyr absorbed by
                    residue
                damr_lyr_2 (float): parameter, fraction of P in lyr absorbed by
                    residue
                minerl_1_1 (float): state variable, surface mineral N
                minerl_1_2 (float): state variable, surface mineral P
                damrmn_1 (float): parameter, minimum C/N ratio allowed in
                    residue after direct absorption
                damrmn_2 (float): parameter, minimum C/P ratio allowed in
                    residue after direct absorption
                pabres (float): parameter, amount of residue which will give
                    maximum direct absorption of N
                frlign (float): fraction of incoming material which is lignin
                spl_1 (float): parameter, intercept of regression predicting
                    fraction of residue going to metabolic
                spl_2 (float): parameter, slope of regression predicting
                    fraction of residue going to metabolic
                rcestr_1 (float): parameter, C/N ratio for structural material
                rcestr_2 (float): parameter, C/P ratio for structural material
                strlig_lyr (float): state variable, lignin in structural
                    material in receiving layer
                strucc_lyr (float): state variable, C in structural material in
                    lyr
                metabc_lyr (float): state variable, C in metabolic material in
                    lyr
                struce_lyr_1 (float): state variable, N in structural material
                    in lyr
                metabe_lyr_1 (float): state variable, N in metabolic material
                    in lyr
                struce_lyr_2 (float): state variable, P in structural material
                    in lyr
                metabe_lyr_2 (float): state variable, P in metabolic material
                    in lyr

            Returns:
                dictionary of values giving modified state variables:
                    mod_minerl_1_1: modified surface mineral N
                    mod_minerl_1_2: modified surface mineral P
                    mod_metabc_lyr: modified METABC_lyr
                    mod_strucc_lyr: modified STRUCC_lyr
                    mod_struce_lyr_1: modified STRUCE_lyr_1
                    mod_metabe_lyr_1: modified METABE_lyr_1
                    mod_struce_lyr_2: modified STRUCE_lyr_2
                    mod_metabe_lyr_2: modified METABE_lyr_2
                    mod_strlig_lyr: modified strlig_lyr

            """
            # calculate direct absorption of mineral N by residue
            if minerl_1_1 < 0:
                dirabs_1 = 0
            else:
                dirabs_1 = damr_lyr_1 * minerl_1_1 * max(cpart / pabres, 1.)
            # rcetot: C/E ratio of incoming material
            if (epart_1 + dirabs_1) <= 0:
                rcetot = 0
            else:
                rcetot = cpart/(epart_1 + dirabs_1)
            if rcetot < damrmn_1:
                dirabs_1 = max(cpart / damrmn_1 - epart_1, 0.)

            # direct absorption of mineral P by residue
            if minerl_1_2 < 0:
                dirabs_2 = 0
            else:
                dirabs_2 = damr_lyr_2 * minerl_1_2 * max(cpart / pabres, 1.)
            # rcetot: C/E ratio of incoming material
            if (epart_2 + dirabs_2) <= 0:
                rcetot = 0
            else:
                rcetot = cpart/(epart_2 + dirabs_2)
            if rcetot < damrmn_2:
                dirabs_2 = max(cpart / damrmn_2 - epart_2, 0.)

            # rlnres: ratio of lignin to N in the incoming material
            rlnres = frlign / ((epart_1 + dirabs_1) / (cpart * 2.5))

            # frmet: fraction of incoming C that goes to metabolic
            frmet = spl_1 - spl_2 * rlnres
            if frlign > (1 - frmet):
                frmet = (1 - frlign)

            # d_metabe_lyr_iel (caddm) is added to metabc_lyr
            d_metabc_lyr = cpart * frmet

            # d_strucc_lyr (cadds) is added to strucc_lyr
            d_strucc_lyr = cpart - d_metabc_lyr

            # d_struce_lyr_1 (eadds_1) is added to STRUCE_lyr_1
            d_struce_lyr_1 = d_strucc_lyr / rcestr_1
            # d_metabe_lyr_1 (eaddm_1) is added to METABE_lyr_1
            d_metabe_lyr_1 = epart_1 + dirabs_1 - d_struce_lyr_1

            # d_struce_lyr_2 (eadds_2) is added to STRUCE_lyr_2
            d_struce_lyr_2 = d_strucc_lyr / rcestr_2
            # d_metabe_lyr_2 (eaddm_2) is added to METABE_lyr_2
            d_metabe_lyr_2 = epart_2 + dirabs_2 - d_struce_lyr_2

            # fligst: fraction of material to structural which is lignin
            # used to update the state variable strlig_lyr, lignin in
            # structural material in the given layer
            fligst = min(frlign / (d_strucc_lyr / cpart), 1.)
            strlig_lyr_mod = (
                ((strlig_lyr * strucc_lyr) + (fligst * d_strucc_lyr)) /
                (strucc_lyr + d_strucc_lyr))
            d_strlig_lyr = strlig_lyr_mod - strlig_lyr

            result_dict = {
                'mod_minerl_1_1': minerl_1_1 - dirabs_1,
                'mod_minerl_1_2': minerl_1_2 - dirabs_2,
                'mod_metabc_lyr': metabc_lyr + d_metabc_lyr,
                'mod_strucc_lyr': strucc_lyr + d_strucc_lyr,
                'mod_struce_lyr_1': struce_lyr_1 + d_struce_lyr_1,
                'mod_metabe_lyr_1': metabe_lyr_1 + d_metabe_lyr_1,
                'mod_struce_lyr_2': struce_lyr_2 + d_struce_lyr_2,
                'mod_metabe_lyr_2': metabe_lyr_2 + d_metabe_lyr_2,
                'mod_strlig_lyr': strlig_lyr + d_strlig_lyr,
            }
            return result_dict
        from rangeland_production import forage
        tolerance = 0.0001

        # known inputs
        cpart = 10.1
        epart_1 = 0.03131
        epart_2 = 0.004242
        damr_lyr_1 = 0.02
        damr_lyr_2 = 0.02
        minerl_1_1 = 40.45
        minerl_1_2 = 24.19
        damrmn_1 = 15.
        damrmn_2 = 150.
        pabres = 100.
        frlign = 0.3
        spl_1 = 0.85
        spl_2 = 0.013
        rcestr_1 = 200.
        rcestr_2 = 500.
        strlig_lyr = 0.224
        strucc_lyr = 157.976
        metabc_lyr = 7.7447
        struce_lyr_1 = 0.8046
        metabe_lyr_1 = 0.4243
        struce_lyr_2 = 0.3152
        metabe_lyr_2 = 0.0555

        # raster inputs
        cpart_path = os.path.join(self.workspace_dir, 'cpart.tif')
        epart_1_path = os.path.join(self.workspace_dir, 'epart_1.tif')
        epart_2_path = os.path.join(self.workspace_dir, 'epart_2.tif')
        frlign_path = os.path.join(self.workspace_dir, 'frlign.tif')
        site_index_path = os.path.join(self.workspace_dir, 'site_index.tif')

        sv_reg = {
            'minerl_1_1_path': os.path.join(
                self.workspace_dir, 'minerl_1_1.tif'),
            'minerl_1_2_path': os.path.join(
                self.workspace_dir, 'minerl_1_2.tif'),
            'metabc_1_path': os.path.join(
                self.workspace_dir, 'metabc.tif'),
            'strucc_1_path': os.path.join(
                self.workspace_dir, 'strucc.tif'),
            'struce_1_1_path': os.path.join(
                self.workspace_dir, 'struce_1_1.tif'),
            'metabe_1_1_path': os.path.join(
                self.workspace_dir, 'metabe_1_1.tif'),
            'struce_1_2_path': os.path.join(
                self.workspace_dir, 'struce_1_2.tif'),
            'metabe_1_2_path': os.path.join(
                self.workspace_dir, 'metabe_1_2.tif'),
            'strlig_1_path': os.path.join(self.workspace_dir, 'strlig.tif')
        }

        create_constant_raster(cpart_path, cpart)
        create_constant_raster(epart_1_path, epart_1)
        create_constant_raster(epart_2_path, epart_2)
        create_constant_raster(frlign_path, frlign)
        create_constant_raster(site_index_path, 1)

        create_constant_raster(sv_reg['minerl_1_1_path'], minerl_1_1)
        create_constant_raster(sv_reg['minerl_1_2_path'], minerl_1_2)
        create_constant_raster(sv_reg['metabc_1_path'], metabc_lyr)
        create_constant_raster(sv_reg['strucc_1_path'], strucc_lyr)
        create_constant_raster(sv_reg['struce_1_1_path'], struce_lyr_1)
        create_constant_raster(sv_reg['metabe_1_1_path'], metabe_lyr_1)
        create_constant_raster(sv_reg['struce_1_2_path'], struce_lyr_2)
        create_constant_raster(sv_reg['metabe_1_2_path'], metabe_lyr_2)
        create_constant_raster(sv_reg['strlig_1_path'], strlig_lyr)

        site_param_table = {
            1: {
                'damr_1_1': damr_lyr_1,
                'damr_1_2': damr_lyr_2,
                'pabres': pabres,
                'damrmn_1': damrmn_1,
                'damrmn_2': damrmn_2,
                'spl_1': spl_1,
                'spl_2': spl_2,
                'rcestr_1': rcestr_1,
                'rcestr_2': rcestr_2,
            }
        }
        lyr = 1

        point_results_dict = partit_point(
            cpart, epart_1, epart_2, damr_lyr_1, damr_lyr_2, minerl_1_1,
            minerl_1_2, damrmn_1, damrmn_2, pabres, frlign, spl_1, spl_2,
            rcestr_1, rcestr_2, strlig_lyr, strucc_lyr, metabc_lyr,
            struce_lyr_1, metabe_lyr_1, struce_lyr_2, metabe_lyr_2)

        forage.partit(
            cpart_path, epart_1_path, epart_2_path, frlign_path,
            site_index_path, site_param_table, lyr, sv_reg)

        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_1_path'],
            point_results_dict['mod_minerl_1_1'] - tolerance,
            point_results_dict['mod_minerl_1_1'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_2_path'],
            point_results_dict['mod_minerl_1_2'] - tolerance,
            point_results_dict['mod_minerl_1_2'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabc_1_path'],
            point_results_dict['mod_metabc_lyr'] - tolerance,
            point_results_dict['mod_metabc_lyr'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strucc_1_path'],
            point_results_dict['mod_strucc_lyr'] - tolerance,
            point_results_dict['mod_strucc_lyr'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_1_path'],
            point_results_dict['mod_struce_lyr_1'] - tolerance,
            point_results_dict['mod_struce_lyr_1'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_1_path'],
            point_results_dict['mod_metabe_lyr_1'] - tolerance,
            point_results_dict['mod_metabe_lyr_1'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_2_path'],
            point_results_dict['mod_struce_lyr_2'] - tolerance,
            point_results_dict['mod_struce_lyr_2'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_2_path'],
            point_results_dict['mod_metabe_lyr_2'] - tolerance,
            point_results_dict['mod_metabe_lyr_2'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strlig_1_path'],
            point_results_dict['mod_strlig_lyr'] - 0.003,
            point_results_dict['mod_strlig_lyr'] + 0.003, _SV_NODATA)

    def test_calc_delta_iel(self):
        """Test `calc_delta_iel`.

        Use the function `calc_delta_iel` to calculate the change in N or P
        accompanying a change in C.  Test that the calculated value matches
        value calculated by hand.

        Raises:
            AssertionError if the value calculated by `calc_delta_iel` does not
                match value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.000001
        array_shape = (10, 10)

        # known inputs
        c_state_variable = 120.5
        iel_state_variable = 39.29
        delta_c = 17.49

        delta_iel = 5.702756

        # array-based inputs
        c_state_variable_ar = numpy.full(array_shape, c_state_variable)
        iel_state_variable_ar = numpy.full(array_shape, iel_state_variable)
        delta_c_ar = numpy.full(array_shape, delta_c)

        delta_iel_ar = forage.calc_delta_iel(
            c_state_variable_ar, iel_state_variable_ar, delta_c_ar)
        self.assert_all_values_in_array_within_range(
            delta_iel_ar, delta_iel - tolerance, delta_iel + tolerance,
            _TARGET_NODATA)

        insert_nodata_values_into_array(c_state_variable_ar, _SV_NODATA)
        insert_nodata_values_into_array(iel_state_variable_ar, _SV_NODATA)
        insert_nodata_values_into_array(delta_c_ar, _TARGET_NODATA)

        delta_iel_ar = forage.calc_delta_iel(
            c_state_variable_ar, iel_state_variable_ar, delta_c_ar)
        self.assert_all_values_in_array_within_range(
            delta_iel_ar, delta_iel - tolerance, delta_iel + tolerance,
            _TARGET_NODATA)

    def test_calc_fall_standing_dead(self):
        """Test `calc_fall_standing_dead`.

        Use the function `calc_fall_standing_dead` to calculate the change in C
        in standing dead as standing dead falls to surface litter. Test that
        the calculated value matches value calculated by hand.

        Raises:
            AssertionError if `calc_fall_standing_dead` does not match value
                calculated by hand

        Returns:
            None
        """
        from rangeland_production import forage
        tolerance = 0.00001
        array_shape = (10, 10)

        # known values
        stdedc = 308.22
        fallrt = 0.15

        delta_c_standing_dead = 46.233

        # array-based inputs
        stdedc_ar = numpy.full(array_shape, stdedc)
        fallrt_ar = numpy.full(array_shape, fallrt)

        delta_c_standing_dead_ar = forage.calc_fall_standing_dead(
            stdedc_ar, fallrt_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_standing_dead_ar, delta_c_standing_dead - tolerance,
            delta_c_standing_dead + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(stdedc_ar, _SV_NODATA)
        insert_nodata_values_into_array(fallrt_ar, _IC_NODATA)

        delta_c_standing_dead_ar = forage.calc_fall_standing_dead(
            stdedc_ar, fallrt_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_standing_dead_ar, delta_c_standing_dead - tolerance,
            delta_c_standing_dead + tolerance, _TARGET_NODATA)

    def test_calc_root_death(self):
        """Test `calc_root_death`.

        Use the function `calc_root_death` to calculate the change in bglivc
        with root death. Test that the calculated value matches values
        calculated by hand.

        Raises:
            AssertionError if `calc_root_death` does not match value calculated
                by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.0001
        array_shape = (10, 10)

        # known values, temperature sufficient for death
        average_temperature = 8.
        rtdtmp = 2.
        rdr = 0.05
        avh2o_1 = 0.1183
        deck5 = 5.
        bglivc = 123.9065

        delta_c_root_death = 6.05213

        # array-based inputs
        average_temperature_ar = numpy.full(array_shape, average_temperature)
        rtdtmp_ar = numpy.full(array_shape, rtdtmp)
        rdr_ar = numpy.full(array_shape, rdr)
        avh2o_1_ar = numpy.full(array_shape, avh2o_1)
        deck5_ar = numpy.full(array_shape, deck5)
        bglivc_ar = numpy.full(array_shape, bglivc)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(average_temperature_ar, _IC_NODATA)
        insert_nodata_values_into_array(rtdtmp_ar, _IC_NODATA)
        insert_nodata_values_into_array(rdr_ar, _IC_NODATA)
        insert_nodata_values_into_array(avh2o_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(deck5_ar, _IC_NODATA)
        insert_nodata_values_into_array(bglivc_ar, _SV_NODATA)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

        # known values, temperature insufficient for death
        average_temperature = -1.
        rtdtmp = 2.
        rdr = 0.05
        avh2o_1 = 0.1183
        deck5 = 5.
        bglivc = 123.9065

        delta_c_root_death = 0.

        # array-based inputs
        average_temperature_ar = numpy.full(array_shape, average_temperature)
        rtdtmp_ar = numpy.full(array_shape, rtdtmp)
        rdr_ar = numpy.full(array_shape, rdr)
        avh2o_1_ar = numpy.full(array_shape, avh2o_1)
        deck5_ar = numpy.full(array_shape, deck5)
        bglivc_ar = numpy.full(array_shape, bglivc)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(average_temperature_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(rdr_ar, _IC_NODATA)
        insert_nodata_values_into_array(avh2o_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(deck5_ar, _IC_NODATA)
        insert_nodata_values_into_array(bglivc_ar, _SV_NODATA)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

        # known values, root death rate limited by default value
        average_temperature = 8.
        rtdtmp = 2.
        rdr = 0.98
        avh2o_1 = 0.1183
        deck5 = 5.
        bglivc = 123.9065

        delta_c_root_death = 117.7112

        # array-based inputs
        average_temperature_ar = numpy.full(array_shape, average_temperature)
        rtdtmp_ar = numpy.full(array_shape, rtdtmp)
        rdr_ar = numpy.full(array_shape, rdr)
        avh2o_1_ar = numpy.full(array_shape, avh2o_1)
        deck5_ar = numpy.full(array_shape, deck5)
        bglivc_ar = numpy.full(array_shape, bglivc)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(average_temperature_ar, _IC_NODATA)
        insert_nodata_values_into_array(rdr_ar, _IC_NODATA)
        insert_nodata_values_into_array(avh2o_1_ar, _SV_NODATA)
        insert_nodata_values_into_array(deck5_ar, _IC_NODATA)
        insert_nodata_values_into_array(bglivc_ar, _SV_NODATA)

        delta_c_root_death_ar = forage.calc_root_death(
            average_temperature_ar, rtdtmp_ar, rdr_ar, avh2o_1_ar, deck5_ar,
            bglivc_ar)
        self.assert_all_values_in_array_within_range(
            delta_c_root_death_ar, delta_c_root_death - tolerance,
            delta_c_root_death + tolerance, _TARGET_NODATA)

    def test_calc_senescence_water_shading(self):
        """Test `calc_senescence_water_shading`.

        Use the function `calc_senescence_water_shading` to calculate shoot
        death due to water stress and shading. Test that the calculated value
        matches value calculated by hand.

        Raises:
            AssertionError if `calc_senescence_water_shading` does not match
                value calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001
        array_shape = (10, 10)

        # known values
        aglivc = 221.59
        bgwfunc = 0.88
        fsdeth_1 = 0.2
        fsdeth_3 = 0.2
        fsdeth_4 = 150.

        fdeth = 0.224

        # array-based inputs
        aglivc_ar = numpy.full(array_shape, aglivc)
        bgwfunc_ar = numpy.full(array_shape, bgwfunc)
        fsdeth_1_ar = numpy.full(array_shape, fsdeth_1)
        fsdeth_3_ar = numpy.full(array_shape, fsdeth_3)
        fsdeth_4_ar = numpy.full(array_shape, fsdeth_4)

        fdeth_ar = forage.calc_senescence_water_shading(
            aglivc_ar, bgwfunc_ar, fsdeth_1_ar, fsdeth_3_ar, fsdeth_4_ar)
        self.assert_all_values_in_array_within_range(
            fdeth_ar, fdeth - tolerance, fdeth + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(aglivc_ar, _SV_NODATA)
        insert_nodata_values_into_array(bgwfunc_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(fsdeth_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(fsdeth_3_ar, _IC_NODATA)
        insert_nodata_values_into_array(fsdeth_4_ar, _IC_NODATA)

        fdeth_ar = forage.calc_senescence_water_shading(
            aglivc_ar, bgwfunc_ar, fsdeth_1_ar, fsdeth_3_ar, fsdeth_4_ar)
        self.assert_all_values_in_array_within_range(
            fdeth_ar, fdeth - tolerance, fdeth + tolerance, _TARGET_NODATA)

    def test_shoot_senescence(self):
        """Test `_shoot_senescence`.

        Use the function `_shoot_senescence` to transition aboveground live
        biomass to standing dead. Test that the calculated value matches
        value calculated by hand.

        Raises:
            AssertionError if `_shoot_senescence` does not match value
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001
        prev_sv_dir = tempfile.mkdtemp(dir=self.workspace_dir)
        cur_sv_dir = tempfile.mkdtemp(dir=self.workspace_dir)

        # known values
        bgwfunc = 0.88
        aglivc = 32.653
        stdedc = 4.4683
        aglive_1 = 0.3
        aglive_2 = 0.1
        stdede_1 = 0.25
        stdede_2 = 0.05
        crpstg_1 = 0
        crpstg_2 = 0

        current_month = 1
        veg_trait_table = {
            1: {
                'senescence_month': 1,
                'fsdeth_1': 0.2,
                'fsdeth_2': 0.75,
                'fsdeth_3': 0.2,
                'fsdeth_4': 150.,
                'vlossp': 0.15,
                'crprtf_1': 0,
                'crprtf_2': 0,
            },
            2: {
                'senescence_month': 4,
                'fsdeth_1': 0.1,
                'fsdeth_2': 0.8,
                'fsdeth_3': 0.17,
                'fsdeth_4': 200.,
                'vlossp': 0.15,
                'crprtf_1': 0.1,
                'crprtf_2': 0.05,
            }
        }
        pft_id_set = set([key for key in veg_trait_table])
        prev_sv_reg = {
            'aglivc_1_path': os.path.join(prev_sv_dir, 'aglivc_1.tif'),
            'aglive_1_1_path': os.path.join(prev_sv_dir, 'aglive_1_1.tif'),
            'aglive_2_1_path': os.path.join(prev_sv_dir, 'aglive_2_1.tif'),
            'crpstg_1_1_path': os.path.join(prev_sv_dir, 'crpstg_1_1.tif'),
            'crpstg_2_1_path': os.path.join(prev_sv_dir, 'crpstg_2_1.tif'),

            'aglivc_2_path': os.path.join(prev_sv_dir, 'aglivc_2.tif'),
            'aglive_1_2_path': os.path.join(prev_sv_dir, 'aglive_1_2.tif'),
            'aglive_2_2_path': os.path.join(prev_sv_dir, 'aglive_2_2.tif'),
            'crpstg_1_2_path': os.path.join(prev_sv_dir, 'crpstg_1_2.tif'),
            'crpstg_2_2_path': os.path.join(prev_sv_dir, 'crpstg_2_2.tif'),
        }
        create_constant_raster(prev_sv_reg['aglivc_1_path'], aglivc)
        create_constant_raster(prev_sv_reg['aglive_1_1_path'], aglive_1)
        create_constant_raster(prev_sv_reg['aglive_2_1_path'], aglive_2)
        create_constant_raster(prev_sv_reg['crpstg_1_1_path'], crpstg_1)
        create_constant_raster(prev_sv_reg['crpstg_2_1_path'], crpstg_2)

        create_constant_raster(prev_sv_reg['aglivc_2_path'], aglivc)
        create_constant_raster(prev_sv_reg['aglive_1_2_path'], aglive_1)
        create_constant_raster(prev_sv_reg['aglive_2_2_path'], aglive_2)
        create_constant_raster(prev_sv_reg['crpstg_1_2_path'], crpstg_1)
        create_constant_raster(prev_sv_reg['crpstg_2_2_path'], crpstg_2)

        sv_reg = {
            'aglivc_1_path': os.path.join(cur_sv_dir, 'aglivc_1.tif'),
            'stdedc_1_path': os.path.join(cur_sv_dir, 'stdedc_1.tif'),
            'aglive_1_1_path': os.path.join(cur_sv_dir, 'aglive_1_1.tif'),
            'aglive_2_1_path': os.path.join(cur_sv_dir, 'aglive_2_1.tif'),
            'stdede_1_1_path': os.path.join(cur_sv_dir, 'stdede_1_1.tif'),
            'stdede_2_1_path': os.path.join(cur_sv_dir, 'stdede_2_1.tif'),
            'crpstg_1_1_path': os.path.join(cur_sv_dir, 'crpstg_1_1.tif'),
            'crpstg_2_1_path': os.path.join(cur_sv_dir, 'crpstg_2_1.tif'),

            'aglivc_2_path': os.path.join(cur_sv_dir, 'aglivc_2.tif'),
            'stdedc_2_path': os.path.join(cur_sv_dir, 'stdedc_2.tif'),
            'aglive_1_2_path': os.path.join(cur_sv_dir, 'aglive_1_2.tif'),
            'aglive_2_2_path': os.path.join(cur_sv_dir, 'aglive_2_2.tif'),
            'stdede_1_2_path': os.path.join(cur_sv_dir, 'stdede_1_2.tif'),
            'stdede_2_2_path': os.path.join(cur_sv_dir, 'stdede_2_2.tif'),
            'crpstg_1_2_path': os.path.join(cur_sv_dir, 'crpstg_1_2.tif'),
            'crpstg_2_2_path': os.path.join(cur_sv_dir, 'crpstg_2_2.tif'),
        }
        month_reg = {
            'bgwfunc': os.path.join(self.workspace_dir, 'bgwfunc.tif'),
        }
        create_constant_raster(month_reg['bgwfunc'], bgwfunc)
        create_constant_raster(sv_reg['stdedc_1_path'], stdedc)
        create_constant_raster(sv_reg['stdedc_2_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_1_path'], stdede_1)
        create_constant_raster(sv_reg['stdede_2_1_path'], stdede_2)
        create_constant_raster(sv_reg['stdede_1_2_path'], stdede_1)
        create_constant_raster(sv_reg['stdede_2_2_path'], stdede_2)

        # known modified state variables
        aglivc_after_1 = 8.16325
        stdedc_after_1 = 28.95805
        aglive_1_after_1 = 0.075
        aglive_2_after_1 = 0.025
        stdede_1_after_1 = 0.44125
        stdede_2_after_1 = 0.125
        crpstg_1_after_1 = 0
        crpstg_2_after_1 = 0

        aglivc_after_2 = 32.261164
        stdedc_after_2 = 4.860136
        aglive_1_after_2 = 0.2964
        aglive_2_after_2 = 0.0988
        stdede_1_after_2 = 0.252754
        stdede_2_after_2 = 0.05114
        crpstg_1_after_2 = 0.000306
        crpstg_2_after_2 = 0.00006

        forage._shoot_senescence(
            pft_id_set, veg_trait_table, prev_sv_reg, month_reg, current_month,
            sv_reg)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], aglivc_after_1 - tolerance,
            aglivc_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdedc_1_path'], stdedc_after_1 - tolerance,
            stdedc_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], aglive_1_after_1 - tolerance,
            aglive_1_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], aglive_2_after_1 - tolerance,
            aglive_2_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_1_1_path'], stdede_1_after_1 - tolerance,
            stdede_1_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_2_1_path'], stdede_2_after_1 - tolerance,
            stdede_2_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_1_1_path'], crpstg_1_after_1 - tolerance,
            crpstg_1_after_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_2_1_path'], crpstg_2_after_1 - tolerance,
            crpstg_2_after_1 + tolerance, _SV_NODATA)

        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_2_path'], aglivc_after_2 - tolerance,
            aglivc_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdedc_2_path'], stdedc_after_2 - tolerance,
            stdedc_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_2_path'], aglive_1_after_2 - tolerance,
            aglive_1_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_2_path'], aglive_2_after_2 - tolerance,
            aglive_2_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_1_2_path'], stdede_1_after_2 - tolerance,
            stdede_1_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_2_2_path'], stdede_2_after_2 - tolerance,
            stdede_2_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_1_2_path'], crpstg_1_after_2 - tolerance,
            crpstg_1_after_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_2_2_path'], crpstg_2_after_2 - tolerance,
            crpstg_2_after_2 + tolerance, _SV_NODATA)

    def test_calc_nutrient_limitation(self):
        """Test `calc_nutrient_limitation`.

        Use the function `calc_nutrient_limitation` to calculate C, N and P in
        new production limited by nutrient availability. Test that calculated
        values match values calculated by point-based version.

        Raises:
            AssertionError if `calc_nutrient_limitation` does not match value
                calculated by point-based version.

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (3, 3)
        tolerance = 0.00001

        # known values, eavail_2 > demand_2 and P is limiting nutrient
        potenc = 200.1
        rtsh = 0.59
        eavail_1 = 200.5
        eavail_2 = 62
        snfxmx_1 = 0.03
        cercrp_max_above_1 = 8
        cercrp_max_below_1 = 11
        cercrp_max_above_2 = 7
        cercrp_max_below_2 = 6
        cercrp_min_above_1 = 3
        cercrp_min_below_1 = 5
        cercrp_min_above_2 = 2
        cercrp_min_below_2 = 2.5

        point_results = calc_nutrient_limitation_point(
            potenc, rtsh, eavail_1, eavail_2, snfxmx_1,
            cercrp_max_above_1, cercrp_max_below_1, cercrp_max_above_2,
            cercrp_max_below_2, cercrp_min_above_1, cercrp_min_below_1,
            cercrp_min_above_2, cercrp_min_below_2)

        # test values for P only against values calculated by hand
        c_production_known = 172.222418488863
        eup_above_2_known = 41.367670329147
        eup_below_2_known = 20.632329670853

        self.assertAlmostEqual(
            point_results['c_production'], c_production_known)
        self.assertAlmostEqual(
            point_results['eup_above_2'], eup_above_2_known)
        self.assertAlmostEqual(
            point_results['eup_below_2'], eup_below_2_known)

        # array-based inputs
        potenc_ar = numpy.full(array_shape, potenc)
        rtsh_ar = numpy.full(array_shape, rtsh)
        eavail_1_ar = numpy.full(array_shape, eavail_1)
        eavail_2_ar = numpy.full(array_shape, eavail_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)
        cercrp_max_above_1_ar = numpy.full(array_shape, cercrp_max_above_1)
        cercrp_max_below_1_ar = numpy.full(array_shape, cercrp_max_below_1)
        cercrp_max_above_2_ar = numpy.full(array_shape, cercrp_max_above_2)
        cercrp_max_below_2_ar = numpy.full(array_shape, cercrp_max_below_2)
        cercrp_min_above_1_ar = numpy.full(array_shape, cercrp_min_above_1)
        cercrp_min_below_1_ar = numpy.full(array_shape, cercrp_min_below_1)
        cercrp_min_above_2_ar = numpy.full(array_shape, cercrp_min_above_2)
        cercrp_min_below_2_ar = numpy.full(array_shape, cercrp_min_below_2)

        cprodl_ar = forage.calc_nutrient_limitation(
            'cprodl')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_1_ar = forage.calc_nutrient_limitation(
            'eup_above_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_1_ar = forage.calc_nutrient_limitation(
            'eup_below_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_2_ar = forage.calc_nutrient_limitation(
            'eup_above_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_2_ar = forage.calc_nutrient_limitation(
            'eup_below_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        plantNfix_ar = forage.calc_nutrient_limitation(
            'plantNfix')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)

        self.assert_all_values_in_array_within_range(
            cprodl_ar, point_results['c_production'] - tolerance,
            point_results['c_production'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_1_ar, point_results['eup_above_1'] - tolerance,
            point_results['eup_above_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_1_ar, point_results['eup_below_1'] - tolerance,
            point_results['eup_below_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_2_ar, point_results['eup_above_2'] - tolerance,
            point_results['eup_above_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_2_ar, point_results['eup_below_2'] - tolerance,
            point_results['eup_below_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            plantNfix_ar, point_results['plantNfix'] - tolerance,
            point_results['plantNfix'] + tolerance, _TARGET_NODATA)

        # known values, eavail_1 < demand_1 and N is limiting nutrient
        potenc = 200.1
        rtsh = 0.59
        eavail_1 = 10.1
        eavail_2 = 62
        snfxmx_1 = 0.003
        cercrp_max_above_1 = 8
        cercrp_max_below_1 = 11
        cercrp_max_above_2 = 7
        cercrp_max_below_2 = 6
        cercrp_min_above_1 = 3
        cercrp_min_below_1 = 5
        cercrp_min_above_2 = 2
        cercrp_min_below_2 = 2.5

        point_results = calc_nutrient_limitation_point(
            potenc, rtsh, eavail_1, eavail_2, snfxmx_1,
            cercrp_max_above_1, cercrp_max_below_1, cercrp_max_above_2,
            cercrp_max_below_2, cercrp_min_above_1, cercrp_min_below_1,
            cercrp_min_above_2, cercrp_min_below_2)

        potenc_ar = numpy.full(array_shape, potenc)
        rtsh_ar = numpy.full(array_shape, rtsh)
        eavail_1_ar = numpy.full(array_shape, eavail_1)
        eavail_2_ar = numpy.full(array_shape, eavail_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)
        cercrp_max_above_1_ar = numpy.full(array_shape, cercrp_max_above_1)
        cercrp_max_below_1_ar = numpy.full(array_shape, cercrp_max_below_1)
        cercrp_max_above_2_ar = numpy.full(array_shape, cercrp_max_above_2)
        cercrp_max_below_2_ar = numpy.full(array_shape, cercrp_max_below_2)
        cercrp_min_above_1_ar = numpy.full(array_shape, cercrp_min_above_1)
        cercrp_min_below_1_ar = numpy.full(array_shape, cercrp_min_below_1)
        cercrp_min_above_2_ar = numpy.full(array_shape, cercrp_min_above_2)
        cercrp_min_below_2_ar = numpy.full(array_shape, cercrp_min_below_2)

        cprodl_ar = forage.calc_nutrient_limitation(
            'cprodl')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_1_ar = forage.calc_nutrient_limitation(
            'eup_above_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_1_ar = forage.calc_nutrient_limitation(
            'eup_below_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_2_ar = forage.calc_nutrient_limitation(
            'eup_above_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_2_ar = forage.calc_nutrient_limitation(
            'eup_below_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        plantNfix_ar = forage.calc_nutrient_limitation(
            'plantNfix')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)

        self.assert_all_values_in_array_within_range(
            cprodl_ar, point_results['c_production'] - tolerance,
            point_results['c_production'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_1_ar, point_results['eup_above_1'] - tolerance,
            point_results['eup_above_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_1_ar, point_results['eup_below_1'] - tolerance,
            point_results['eup_below_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_2_ar, point_results['eup_above_2'] - tolerance,
            point_results['eup_above_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_2_ar, point_results['eup_below_2'] - tolerance,
            point_results['eup_below_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            plantNfix_ar, point_results['plantNfix'] - tolerance,
            point_results['plantNfix'] + tolerance, _TARGET_NODATA)

        insert_nodata_values_into_array(potenc_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(rtsh_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(eavail_1_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(eavail_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(snfxmx_1_ar, _IC_NODATA)
        insert_nodata_values_into_array(cercrp_max_below_1_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(cercrp_min_above_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(cercrp_min_below_2_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(cercrp_max_above_1_ar, _TARGET_NODATA)

        cprodl_ar = forage.calc_nutrient_limitation(
            'cprodl')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_1_ar = forage.calc_nutrient_limitation(
            'eup_above_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_1_ar = forage.calc_nutrient_limitation(
            'eup_below_1')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_above_2_ar = forage.calc_nutrient_limitation(
            'eup_above_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        eup_below_2_ar = forage.calc_nutrient_limitation(
            'eup_below_2')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)
        plantNfix_ar = forage.calc_nutrient_limitation(
            'plantNfix')(
            potenc_ar, rtsh_ar, eavail_1_ar, eavail_2_ar,
            snfxmx_1_ar,
            cercrp_max_above_1_ar, cercrp_max_below_1_ar,
            cercrp_max_above_2_ar, cercrp_max_below_2_ar,
            cercrp_min_above_1_ar, cercrp_min_below_1_ar,
            cercrp_min_above_2_ar, cercrp_min_below_2_ar)

        self.assert_all_values_in_array_within_range(
            cprodl_ar, point_results['c_production'] - tolerance,
            point_results['c_production'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_1_ar, point_results['eup_above_1'] - tolerance,
            point_results['eup_above_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_1_ar, point_results['eup_below_1'] - tolerance,
            point_results['eup_below_1'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_above_2_ar, point_results['eup_above_2'] - tolerance,
            point_results['eup_above_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            eup_below_2_ar, point_results['eup_below_2'] - tolerance,
            point_results['eup_below_2'] + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_array_within_range(
            plantNfix_ar, point_results['plantNfix'] - tolerance,
            point_results['plantNfix'] + tolerance, _TARGET_NODATA)

    def test_nutrient_uptake(self):
        """Test `nutrient_uptake`.

        Use the function `nutrient_uptake` to calculate flow of N or P
        from soil and crop storage to above and belowground live biomass.
        Test that calculated values match values calculated by point-based
        version.

        Raises:
            AssertionError if `nutrient_uptake` does not match values
                calculated by point-based version

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known values: iel=1, some uptake from soil, some plant N fixation
        iel = 1.
        nlay = 4
        availm = 51.
        eavail = 54.2
        percent_cover = 0.4
        eup_above_iel = 41.367670329147
        eup_below_iel = 20.632329670853
        storage_iel = 40.48
        plantNfix = 8.048
        pslsrb = 1.
        sorpmx = 2.
        aglive_iel = 80.8
        bglive_iel = 130.6
        minerl_dict = {
            'minerl_1_iel': 10.,
            'minerl_2_iel': 13.,
            'minerl_3_iel': 20.,
            'minerl_4_iel': 8.,
            'minerl_5_iel': 30.,
            'minerl_6_iel': 22.,
            'minerl_7_iel': 18.,
        }
        delta_aglive_iel_known = 36.163350513545
        bglive_iel_known = 148.636649486455
        storage_iel_known = 0.
        minerl_1_iel_known = 9.55513725490196
        minerl_2_iel_known = 12.4216784313726
        minerl_3_iel_known = 19.1102745098039
        minerl_4_iel_known = 7.64410980392157
        minerl_5_iel_known = 30
        minerl_6_iel_known = 22
        minerl_7_iel_known = 18

        point_results = nutrient_uptake_point(
            iel, nlay, availm, eavail, percent_cover, eup_above_iel,
            eup_below_iel, storage_iel, plantNfix, pslsrb, sorpmx, aglive_iel,
            bglive_iel, minerl_dict)

        # test point results against known values calculated by hand
        self.assertAlmostEqual(
            point_results['delta_aglive_iel'], delta_aglive_iel_known)
        self.assertAlmostEqual(
            point_results['aglive_iel'], aglive_iel)
        self.assertAlmostEqual(
            point_results['bglive_iel'], bglive_iel_known)
        self.assertAlmostEqual(
            point_results['storage_iel'], storage_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_1_iel'], minerl_1_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_2_iel'], minerl_2_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_3_iel'], minerl_3_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_4_iel'], minerl_4_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_5_iel'], minerl_5_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_6_iel'], minerl_6_iel_known)
        self.assertAlmostEqual(
            point_results['minerl_7_iel'], minerl_7_iel_known)

        # raster-based inputs
        pft_i = 1
        percent_cover_path = os.path.join(self.workspace_dir, 'perc_cover.tif')
        eup_above_iel_path = os.path.join(self.workspace_dir, 'eup_above.tif')
        eup_below_iel_path = os.path.join(self.workspace_dir, 'eup_below.tif')
        plantNfix_path = os.path.join(self.workspace_dir, 'plantNfix.tif')
        availm_path = os.path.join(self.workspace_dir, 'availm.tif')
        eavail_path = os.path.join(self.workspace_dir, 'eavail.tif')
        pslsrb_path = os.path.join(self.workspace_dir, 'pslsrb.tif')
        sorpmx_path = os.path.join(self.workspace_dir, 'sorpmx.tif')
        delta_aglive_iel_path = os.path.join(
            self.workspace_dir, 'delta_aglive.tif')

        sv_reg = {
            'aglive_{}_{}_path'.format(iel, pft_i): os.path.join(
                self.workspace_dir, 'aglive.tif'),
            'bglive_{}_{}_path'.format(iel, pft_i): os.path.join(
                self.workspace_dir, 'bglive.tif'),
            'crpstg_{}_{}_path'.format(iel, pft_i): os.path.join(
                self.workspace_dir, 'crpstg.tif'),
            'minerl_1_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_1.tif'),
            'minerl_2_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_2.tif'),
            'minerl_3_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_3.tif'),
            'minerl_4_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_4.tif'),
            'minerl_5_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_5.tif'),
            'minerl_6_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_6.tif'),
            'minerl_7_{}_path'.format(iel): os.path.join(
                self.workspace_dir, 'minerl_7.tif'),
        }
        create_constant_raster(percent_cover_path, percent_cover)
        create_constant_raster(eup_above_iel_path, eup_above_iel)
        create_constant_raster(eup_below_iel_path, eup_below_iel)
        create_constant_raster(plantNfix_path, plantNfix)
        create_constant_raster(availm_path, availm)
        create_constant_raster(eavail_path, eavail)
        create_constant_raster(
            sv_reg['aglive_{}_{}_path'.format(iel, pft_i)], aglive_iel)
        create_constant_raster(
            sv_reg['bglive_{}_{}_path'.format(iel, pft_i)], bglive_iel)
        create_constant_raster(
            sv_reg['crpstg_{}_{}_path'.format(iel, pft_i)], storage_iel)
        for lyr in range(1, 8):
            create_constant_raster(
                sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                minerl_dict['minerl_{}_iel'.format(lyr)])
        create_constant_raster(pslsrb_path, pslsrb)
        create_constant_raster(sorpmx_path, sorpmx)

        forage.nutrient_uptake(
            iel, nlay, percent_cover_path, eup_above_iel_path,
            eup_below_iel_path, plantNfix_path, availm_path, eavail_path,
            pft_i, pslsrb_path, sorpmx_path, sv_reg, delta_aglive_iel_path)
        self.assert_all_values_in_raster_within_range(
            delta_aglive_iel_path,
            point_results['delta_aglive_iel'] - tolerance,
            point_results['delta_aglive_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_{}_{}_path'.format(iel, pft_i)],
            point_results['aglive_iel'] - tolerance,
            point_results['aglive_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['bglive_{}_{}_path'.format(iel, pft_i)],
            point_results['bglive_iel'] - tolerance,
            point_results['bglive_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_{}_{}_path'.format(iel, pft_i)],
            point_results['storage_iel'] - tolerance,
            point_results['storage_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_{}_path'.format(iel)],
            point_results['minerl_1_iel'] - tolerance,
            point_results['minerl_1_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_2_{}_path'.format(iel)],
            point_results['minerl_2_iel'] - tolerance,
            point_results['minerl_2_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_3_{}_path'.format(iel)],
            point_results['minerl_3_iel'] - tolerance,
            point_results['minerl_3_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_4_{}_path'.format(iel)],
            point_results['minerl_4_iel'] - tolerance,
            point_results['minerl_4_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_5_{}_path'.format(iel)],
            point_results['minerl_5_iel'] - tolerance,
            point_results['minerl_5_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_6_{}_path'.format(iel)],
            point_results['minerl_6_iel'] - tolerance,
            point_results['minerl_6_iel'] + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_7_{}_path'.format(iel)],
            point_results['minerl_7_iel'] - tolerance,
            point_results['minerl_7_iel'] + tolerance, _SV_NODATA)

    def test_restrict_potential_growth(self):
        """Test `restrict_potential_growth`.

        Use the function `restrict_potential_growth` to restrict potential
        growth according to the availability of mineral N and P. Test that
        calculated growth matches values calculated by hand.

        Raises:
            AssertionError if restrict_potential_growth does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (3, 3)
        tolerance = 0.00000001

        # known inputs: no available mineral N
        potenc = 100
        availm_1 = 0.
        availm_2 = 20.
        snfxmx_1 = 0.
        potenc_lim_minerl = 0.

        # array-based inputs
        potenc_ar = numpy.full(array_shape, potenc)
        availm_1_ar = numpy.full(array_shape, availm_1)
        availm_2_ar = numpy.full(array_shape, availm_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)

        potenc_lim_minerl_ar = forage.restrict_potential_growth(
            potenc_ar, availm_1_ar, availm_2_ar, snfxmx_1_ar)
        self.assert_all_values_in_array_within_range(
            potenc_lim_minerl_ar, potenc_lim_minerl - tolerance,
            potenc_lim_minerl + tolerance, _TARGET_NODATA)

        # N supplied by N fixation
        potenc = 100.
        availm_1 = 0.
        availm_2 = 20.
        snfxmx_1 = 10.
        potenc_lim_minerl = potenc

        potenc_ar = numpy.full(array_shape, potenc)
        availm_1_ar = numpy.full(array_shape, availm_1)
        availm_2_ar = numpy.full(array_shape, availm_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)

        potenc_lim_minerl_ar = forage.restrict_potential_growth(
            potenc_ar, availm_1_ar, availm_2_ar, snfxmx_1_ar)
        self.assert_all_values_in_array_within_range(
            potenc_lim_minerl_ar, potenc_lim_minerl - tolerance,
            potenc_lim_minerl + tolerance, _TARGET_NODATA)

        # N supplied by mineral source
        potenc = 100.
        availm_1 = 10.
        availm_2 = 20.
        snfxmx_1 = 0.
        potenc_lim_minerl = potenc

        potenc_ar = numpy.full(array_shape, potenc)
        availm_1_ar = numpy.full(array_shape, availm_1)
        availm_2_ar = numpy.full(array_shape, availm_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)

        potenc_lim_minerl_ar = forage.restrict_potential_growth(
            potenc_ar, availm_1_ar, availm_2_ar, snfxmx_1_ar)
        self.assert_all_values_in_array_within_range(
            potenc_lim_minerl_ar, potenc_lim_minerl - tolerance,
            potenc_lim_minerl + tolerance, _TARGET_NODATA)

        # no available P
        potenc = 100.
        availm_1 = 10.
        availm_2 = 0.
        snfxmx_1 = 0.
        potenc_lim_minerl = 0.

        potenc_ar = numpy.full(array_shape, potenc)
        availm_1_ar = numpy.full(array_shape, availm_1)
        availm_2_ar = numpy.full(array_shape, availm_2)
        snfxmx_1_ar = numpy.full(array_shape, snfxmx_1)

        potenc_lim_minerl_ar = forage.restrict_potential_growth(
            potenc_ar, availm_1_ar, availm_2_ar, snfxmx_1_ar)
        self.assert_all_values_in_array_within_range(
            potenc_lim_minerl_ar, potenc_lim_minerl - tolerance,
            potenc_lim_minerl + tolerance, _TARGET_NODATA)

    def test_c_uptake_aboveground(self):
        """Test `c_uptake_aboveground`.

        Use the function `c_uptake_aboveground` to calculate the change in C in
        aboveground live biomass.  Test that the function matches values
        calculated by hand.

        Raises:
            AssertionError if `c_uptake_aboveground` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        array_shape = (3, 3)
        tolerance = 0.00001

        # known inputs
        cprodl = 20.2
        rtsh = 0.6
        delta_aglivc = 12.625

        # array-based inputs
        cprodl_ar = numpy.full(array_shape, cprodl)
        rtsh_ar = numpy.full(array_shape, rtsh)

        delta_aglivc_ar = forage.c_uptake_aboveground(cprodl_ar, rtsh_ar)
        self.assert_all_values_in_array_within_range(
            delta_aglivc_ar, delta_aglivc - tolerance,
            delta_aglivc + tolerance, _SV_NODATA)

        insert_nodata_values_into_array(cprodl_ar, _TARGET_NODATA)
        insert_nodata_values_into_array(rtsh_ar, _TARGET_NODATA)

        delta_aglivc_ar = forage.c_uptake_aboveground(cprodl_ar, rtsh_ar)
        self.assert_all_values_in_array_within_range(
            delta_aglivc_ar, delta_aglivc - tolerance,
            delta_aglivc + tolerance, _SV_NODATA)

    def test_new_growth(self):
        """Test `_new_growth`.

        Use the function `new_growth` to calculate growth of new above and
        belowground biomass. Test that state variables for plant functional
        types scheduled to senesce do not experience new growth. Test that
        above and belowground biomass increases for plant functional types
        not scheduled to senesce.

        Raises:
            AssertionError if `new_growth` produces change in biomass for
                pft scheduled to senesce
            AssertionError if `new_growth` fails to produce change in biomass
                for pft not scheduled to senesce

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known values
        initial_aglivc = 25.72
        initial_bglivc = 156.4
        initial_aglive_1 = 0.41
        initial_aglive_2 = 0.32
        initial_bglive_1 = 3.281
        initial_bglive_2 = 0.372
        initial_crpstg_1 = 0.03
        initial_crpstg_2 = 0.01
        initial_minerl_1 = 6.33
        initial_minerl_2 = 14.38

        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
            'pft_2': os.path.join(self.workspace_dir, 'pft_2.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['pft_1'], 0.3)
        create_constant_raster(aligned_inputs['pft_2'], 0.6)
        site_param_table = {
            1: {
                'favail_1': 0.9,
                'favail_4': 0.2,
                'favail_5': 0.5,
                'favail_6': 2.3,
                'rictrl': 0.013,
                'riint': 0.65,
                'sorpmx': 2,
                'pslsrb': 1,
            }
        }
        veg_trait_table = {
            1: {
                'snfxmx_1': 0.03,
                'senescence_month': 3,
                'nlaypg': 5,
                'growth_months': ['4', '5', '6'],
            },
            2: {
                'snfxmx_1': 0.004,
                'senescence_month': 5,
                'nlaypg': 3,
                'growth_months': ['3', '4'],
            }
        }
        sv_reg = {
            'minerl_1_1_path': os.path.join(
                self.workspace_dir, 'minerl_1_1.tif'),
            'minerl_2_1_path': os.path.join(
                self.workspace_dir, 'minerl_2_1.tif'),
            'minerl_3_1_path': os.path.join(
                self.workspace_dir, 'minerl_3_1.tif'),
            'minerl_4_1_path': os.path.join(
                self.workspace_dir, 'minerl_4_1.tif'),
            'minerl_5_1_path': os.path.join(
                self.workspace_dir, 'minerl_5_1.tif'),
            'minerl_1_2_path': os.path.join(
                self.workspace_dir, 'minerl_1_2.tif'),
            'minerl_2_2_path': os.path.join(
                self.workspace_dir, 'minerl_2_2.tif'),
            'minerl_3_2_path': os.path.join(
                self.workspace_dir, 'minerl_3_2.tif'),
            'minerl_4_2_path': os.path.join(
                self.workspace_dir, 'minerl_4_2.tif'),
            'minerl_5_2_path': os.path.join(
                self.workspace_dir, 'minerl_5_2.tif'),
        }
        for lyr in range(1, 6):
            create_constant_raster(
                sv_reg['minerl_{}_1_path'.format(lyr)],
                initial_minerl_1)
            create_constant_raster(
                sv_reg['minerl_{}_2_path'.format(lyr)],
                initial_minerl_2)
        for pft_i in [1, 2]:
            sv_reg['aglivc_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'aglivc_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['aglivc_{}_path'.format(pft_i)], initial_aglivc)
            sv_reg['bglivc_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'bglivc_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['bglivc_{}_path'.format(pft_i)], initial_bglivc)
            sv_reg['aglive_1_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'aglive_1_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['aglive_1_{}_path'.format(pft_i)], initial_aglive_1)
            sv_reg['aglive_2_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'aglive_2_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['aglive_2_{}_path'.format(pft_i)], initial_aglive_2)
            sv_reg['bglive_1_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'bglive_1_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['bglive_1_{}_path'.format(pft_i)], initial_bglive_1)
            sv_reg['bglive_2_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'bglive_2_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['bglive_2_{}_path'.format(pft_i)], initial_bglive_2)
            sv_reg['crpstg_1_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'crpstg_1_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['crpstg_1_{}_path'.format(pft_i)], initial_crpstg_1)
            sv_reg['crpstg_2_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'crpstg_2_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['crpstg_2_{}_path'.format(pft_i)], initial_crpstg_2)
            sv_reg['crpstg_1_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'crpstg_1_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['crpstg_1_{}_path'.format(pft_i)], initial_crpstg_1)
            sv_reg['crpstg_2_{}_path'.format(pft_i)] = os.path.join(
                self.workspace_dir, 'crpstg_2_{}.tif'.format(pft_i))
            create_constant_raster(
                sv_reg['crpstg_2_{}_path'.format(pft_i)], initial_crpstg_2)

        month_reg = {
            'tgprod_pot_prod_1': os.path.join(
                self.workspace_dir, 'tgprod_pot_prod_1.tif'),
            'rtsh_1': os.path.join(
                self.workspace_dir, 'rtsh_1.tif'),
            'tgprod_pot_prod_2': os.path.join(
                self.workspace_dir, 'tgprod_pot_prod_2.tif'),
            'rtsh_2': os.path.join(
                self.workspace_dir, 'rtsh_2.tif'),
        }
        for pft_i in [1, 2]:
            for iel in [1, 2]:
                month_reg['cercrp_min_above_{}_{}'.format(
                    iel, pft_i)] = os.path.join(
                    self.workspace_dir, 'cercrp_min_above_{}_{}.tif'.format(
                        iel, pft_i))
                month_reg['cercrp_max_above_{}_{}'.format(
                    iel, pft_i)] = os.path.join(
                    self.workspace_dir, 'cercrp_max_above_{}_{}.tif'.format(
                        iel, pft_i))
                month_reg['cercrp_min_below_{}_{}'.format(
                    iel, pft_i)] = os.path.join(
                    self.workspace_dir, 'cercrp_min_below_{}_{}.tif'.format(
                        iel, pft_i))
                month_reg['cercrp_max_below_{}_{}'.format(
                    iel, pft_i)] = os.path.join(
                    self.workspace_dir, 'cercrp_max_below_{}_{}.tif'.format(
                        iel, pft_i))
        create_constant_raster(month_reg['tgprod_pot_prod_1'], 426.04)
        create_constant_raster(month_reg['rtsh_1'], 0.3)
        create_constant_raster(month_reg['tgprod_pot_prod_2'], 341.04)
        create_constant_raster(month_reg['rtsh_2'], 0.6)
        for pft_i in [1, 2]:
            for iel in [1, 2]:
                create_constant_raster(
                    month_reg['cercrp_min_above_{}_{}'.format(iel, pft_i)],
                    30.2)
                create_constant_raster(
                    month_reg['cercrp_max_above_{}_{}'.format(iel, pft_i)],
                    94.2)
                create_constant_raster(
                    month_reg['cercrp_min_below_{}_{}'.format(iel, pft_i)],
                    37.1)
                create_constant_raster(
                    month_reg['cercrp_max_below_{}_{}'.format(iel, pft_i)],
                    56.29)

        pft_id_set = set([1, 2])
        current_month = 3

        delta_agliv_dict = forage._new_growth(
            pft_id_set, aligned_inputs, site_param_table, veg_trait_table,
            month_reg, current_month, sv_reg)

        # no growth for pft 1
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglivc_1'], 0 - tolerance,
            0 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglive_1_1'], 0 - tolerance,
            0 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglive_2_1'], 0 - tolerance,
            0 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], initial_aglivc - tolerance,
            initial_aglivc + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['bglivc_1_path'], initial_bglivc - tolerance,
            initial_bglivc + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], initial_aglive_1 - tolerance,
            initial_aglive_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], initial_aglive_2 - tolerance,
            initial_aglive_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_1_1_path'], initial_crpstg_1 - tolerance,
            initial_crpstg_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_2_1_path'], initial_crpstg_2 - tolerance,
            initial_crpstg_2 + tolerance, _SV_NODATA)

        # growth expected for pft 2
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglivc_2'], 10 - tolerance,
            100 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglive_1_2'], 2 - tolerance,
            20 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            delta_agliv_dict['delta_aglive_2_2'], 2 - tolerance,
            20 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_2_path'], initial_aglivc - tolerance,
            initial_aglivc + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['bglivc_2_path'], initial_bglivc + 10,
            initial_bglivc + 100, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_2_path'], initial_aglive_1 - tolerance,
            initial_aglive_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_2_path'], initial_aglive_2 - tolerance,
            initial_aglive_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_1_2_path'], -tolerance, tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['crpstg_2_2_path'], -tolerance, tolerance, _SV_NODATA)

        # uptake expected from mineral layers 1-3
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_1_path'], 0, initial_minerl_1 - 0.2, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_2_1_path'], 0, initial_minerl_1 - 0.2, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_3_1_path'], 0, initial_minerl_1 - 0.2, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_2_path'], 0, initial_minerl_2 - 0.2, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_2_2_path'], 0, initial_minerl_2 - 0.2, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_3_2_path'], 0, initial_minerl_2 - 0.2, _SV_NODATA)

        # no uptake expected from mineral layers 4-5
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_4_1_path'], initial_minerl_1 - tolerance,
            initial_minerl_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_5_1_path'], initial_minerl_1 - tolerance,
            initial_minerl_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_4_2_path'], initial_minerl_2 - tolerance,
            initial_minerl_2 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_5_2_path'], initial_minerl_2 - tolerance,
            initial_minerl_2 + tolerance, _SV_NODATA)

    def test_leaching(self):
        """Test `leach`.

        Use the function `leach` to calculate N or P leaching through soil
        layers. Compare calculated change in mineral N or P to values
        calculated by point-based version.

        Raises:
            AssertionError if `leach` does not match results calculated by
            point-based version

        Returns:
            None

        """
        def leach_point(
                starting_mineral_dict, amov_dict, sand, minlch, fleach_1,
                fleach_2, fleach_3, fleach_4, pslsrb, sorpmx):
            """Point-based implementation of `leach`.

            Returns:
                dictionary of modified mineral element content of each soil
                    layer

            """
            ending_minerl_dict = starting_minerl_dict.copy()
            fsol = fsfunc_point(
                starting_minerl_dict['minerl_1_2'], pslsrb, sorpmx)
            for iel in [1, 2]:
                if iel == 1:
                    frlech = (fleach_1 + fleach_2 * sand) * fleach_3
                else:
                    frlech = (fleach_1 + fleach_2 * sand) * fleach_4 * fsol
                for lyr in range(1, 5):
                    linten = numpy.clip(
                        1 - (minlch - amov_dict['amov_{}'.format(lyr)]) /
                        minlch, 0., 1.)
                    amount_leached = (
                        frlech *
                        ending_minerl_dict['minerl_{}_{}'.format(lyr, iel)] *
                        linten)
                    ending_minerl_dict['minerl_{}_{}'.format(lyr, iel)] = (
                        ending_minerl_dict[
                            'minerl_{}_{}'.format(lyr, iel)] - amount_leached)
                    try:
                        ending_minerl_dict[
                            'minerl_{}_{}'.format(lyr + 1, iel)] = (
                            ending_minerl_dict[
                                'minerl_{}_{}'.format(lyr + 1, iel)] +
                            amount_leached)
                    except KeyError:
                        # nutrient leaving bottom layer does not need to be
                        # tracked
                        pass
            return ending_minerl_dict

        from rangeland_production import forage
        tolerance = 0.00001

        # known values, no leaching of P
        starting_minerl_dict = {
            'minerl_1_1': 10.,
            'minerl_2_1': 10.,
            'minerl_3_1': 10.,
            'minerl_4_1': 10.,
            'minerl_1_2': 10.,
            'minerl_2_2': 10.,
            'minerl_3_2': 10.,
            'minerl_4_2': 10.,
            }
        amov_dict = {
            'amov_1': 19.,
            'amov_2': 10.,
            'amov_3': 23.,
            'amov_4': 19.,
            }
        sand = 0.48375
        minlch = 18.
        fleach_1 = 0.2
        fleach_2 = 0.7
        fleach_3 = 1.
        fleach_4 = 0.
        pslsrb = 1
        sorpmx = 2

        minerl_dict_point = leach_point(
            starting_minerl_dict, amov_dict, sand, minlch, fleach_1,
            fleach_2, fleach_3, fleach_4, pslsrb, sorpmx)

        # raster-based inputs
        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'sand': os.path.join(self.workspace_dir, 'sand.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['sand'], sand)
        site_param_table = {
            1: {
                'minlch': minlch,
                'fleach_1': fleach_1,
                'fleach_2': fleach_2,
                'fleach_3': fleach_3,
                'fleach_4': fleach_4,
                'pslsrb': pslsrb,
                'sorpmx': sorpmx,
                'nlayer': 4,
            }
        }
        sv_reg = {}
        for iel in [1, 2]:
            for lyr in range(1, 5):
                sv_reg['minerl_{}_{}_path'.format(lyr, iel)] = os.path.join(
                    self.workspace_dir, 'minerl_{}_{}.tif'.format(lyr, iel))
                create_constant_raster(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    starting_minerl_dict['minerl_{}_{}'.format(lyr, iel)])
        month_reg = {}
        for lyr in range(1, 5):
            month_reg['amov_{}'.format(lyr)] = os.path.join(
                self.workspace_dir, 'amov_{}.tif'.format(lyr))
            create_constant_raster(
                month_reg['amov_{}'.format(lyr)],
                amov_dict['amov_{}'.format(lyr)])

        forage._leach(aligned_inputs, site_param_table, month_reg, sv_reg)
        for iel in [1, 2]:
            for lyr in range(1, 5):
                self.assert_all_values_in_raster_within_range(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    minerl_dict_point['minerl_{}_{}'.format(lyr, iel)] -
                    tolerance,
                    minerl_dict_point['minerl_{}_{}'.format(lyr, iel)] +
                    tolerance, _SV_NODATA)

        # some leaching of P
        starting_minerl_dict = {
            'minerl_1_1': 13.,
            'minerl_2_1': 10.,
            'minerl_3_1': 8.,
            'minerl_4_1': 9.5,
            'minerl_1_2': 12.3,
            'minerl_2_2': 10.,
            'minerl_3_2': 7.2,
            'minerl_4_2': 2.1,
            }
        amov_dict = {
            'amov_1': 12.,
            'amov_2': 20.,
            'amov_3': 23.,
            'amov_4': 19.,
            }
        sand = 0.48375
        minlch = 18.
        fleach_1 = 0.2
        fleach_2 = 0.7
        fleach_3 = 0.2
        fleach_4 = 0.7
        pslsrb = 1
        sorpmx = 2

        minerl_dict_point = leach_point(
            starting_minerl_dict, amov_dict, sand, minlch, fleach_1,
            fleach_2, fleach_3, fleach_4, pslsrb, sorpmx)

        # raster-based inputs
        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'sand': os.path.join(self.workspace_dir, 'sand.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['sand'], sand)
        site_param_table = {
            1: {
                'minlch': minlch,
                'fleach_1': fleach_1,
                'fleach_2': fleach_2,
                'fleach_3': fleach_3,
                'fleach_4': fleach_4,
                'pslsrb': pslsrb,
                'sorpmx': sorpmx,
                'nlayer': 4,
            }
        }
        sv_reg = {}
        for iel in [1, 2]:
            for lyr in range(1, 5):
                sv_reg['minerl_{}_{}_path'.format(lyr, iel)] = os.path.join(
                    self.workspace_dir, 'minerl_{}_{}.tif'.format(lyr, iel))
                create_constant_raster(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    starting_minerl_dict['minerl_{}_{}'.format(lyr, iel)])
        month_reg = {}
        for lyr in range(1, 5):
            month_reg['amov_{}'.format(lyr)] = os.path.join(
                self.workspace_dir, 'amov_{}.tif'.format(lyr))
            create_constant_raster(
                month_reg['amov_{}'.format(lyr)],
                amov_dict['amov_{}'.format(lyr)])

        forage._leach(aligned_inputs, site_param_table, month_reg, sv_reg)
        for iel in [1, 2]:
            for lyr in range(1, 5):
                self.assert_all_values_in_raster_within_range(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    minerl_dict_point['minerl_{}_{}'.format(lyr, iel)] -
                    tolerance,
                    minerl_dict_point['minerl_{}_{}'.format(lyr, iel)] +
                    tolerance, _SV_NODATA)

        # match Century
        starting_minerl_dict = {
            'minerl_1_1': 7.96845627,
            'minerl_2_1': 0.,
            'minerl_3_1': 0.,
            'minerl_4_1': 0.,
            'minerl_1_2': 13.826642,
            'minerl_2_2': 0.,
            'minerl_3_2': 0.,
            'minerl_4_2': 0.,
            }
        amov_dict = {
            'amov_1': 0.146463394,
            'amov_2': 0,
            'amov_3': 0,
            'amov_4': 0,
            }
        sand = 0.43999
        minlch = 18.
        fleach_1 = 0.2
        fleach_2 = 0.7
        fleach_3 = 1.
        fleach_4 = 0.
        pslsrb = 1
        sorpmx = 2

        # raster-based inputs
        create_constant_raster(aligned_inputs['sand'], sand)
        for iel in [1, 2]:
            for lyr in range(1, 5):
                create_constant_raster(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    starting_minerl_dict['minerl_{}_{}'.format(lyr, iel)])
        for lyr in range(1, 5):
            create_constant_raster(
                month_reg['amov_{}'.format(lyr)],
                amov_dict['amov_{}'.format(lyr)])
        site_param_table = {
            1: {
                'minlch': minlch,
                'fleach_1': fleach_1,
                'fleach_2': fleach_2,
                'fleach_3': fleach_3,
                'fleach_4': fleach_4,
                'pslsrb': pslsrb,
                'sorpmx': sorpmx,
                'nlayer': 4,
            }
        }
        forage._leach(aligned_inputs, site_param_table, month_reg, sv_reg)

        # known outputs from Century
        ending_minerl_dict = {
            'minerl_1_1': 7.93551874,
            'minerl_2_1': 0.032937,
            'minerl_3_1': 0.,
            'minerl_4_1': 0.,
            'minerl_1_2': 13.826642,
            'minerl_2_2': 0.,
            'minerl_3_2': 0.,
            'minerl_4_2': 0.,
        }

        for iel in [1, 2]:
            for lyr in range(1, 5):
                self.assert_all_values_in_raster_within_range(
                    sv_reg['minerl_{}_{}_path'.format(lyr, iel)],
                    ending_minerl_dict['minerl_{}_{}'.format(lyr, iel)] -
                    tolerance,
                    ending_minerl_dict['minerl_{}_{}'.format(lyr, iel)] +
                    tolerance, _SV_NODATA)

    def test_grazing(self):
        """Test `_grazing`.

        Use the function `_grazing` to calculate change in aboveground live
        and dead biomass and return of nutrients to soil with grazing.
        Compare calculated change in state variables to values calculated by
        hand.

        Raises:
            AssertionError if `_grazing` does not match values calculated by
            hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known inputs: one pft
        clay = 0.18

        aglivc = 6.84782124
        aglive_1 = 0.318333626
        aglive_2 = 0.00915864483
        stdedc = 4.27673721
        stdede_1 = 0.167467803
        stdede_2 = 0.00570994569
        minerl_1_1 = 40.45
        minerl_1_2 = 24.19
        strucc_lyr = 157.976
        metabc_lyr = 7.7447
        struce_lyr_1 = 0.8046
        metabe_lyr_1 = 0.4243
        struce_lyr_2 = 0.3152
        metabe_lyr_2 = 0.0555
        strlig_lyr = 0.224

        damr_lyr_1 = 0.02
        damr_lyr_2 = 0.02
        pabres = 100.
        damrmn_1 = 15.
        damrmn_2 = 150.
        spl_1 = 0.85
        spl_2 = 0.013
        rcestr_1 = 200.
        rcestr_2 = 500.

        gfcret = 0.3
        gret_2 = 0.95
        fecf_1 = 0.5
        fecf_2 = 0.9
        feclig = 0.25

        flgrem = 0.1
        fdgrem = 0.05

        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'animal_index': os.path.join(self.workspace_dir, 'animal.tif'),
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
            'clay': os.path.join(self.workspace_dir, 'clay.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['animal_index'], 1)
        create_constant_raster(aligned_inputs['pft_1'], 1)
        create_constant_raster(aligned_inputs['clay'], clay)
        site_param_table = {
            1: {
                'damr_1_1': damr_lyr_1,
                'damr_1_2': damr_lyr_2,
                'pabres': pabres,
                'damrmn_1': damrmn_1,
                'damrmn_2': damrmn_2,
                'spl_1': spl_1,
                'spl_2': spl_2,
                'rcestr_1': rcestr_1,
                'rcestr_2': rcestr_2,
            }
        }
        sv_reg = {
            'aglivc_1_path': os.path.join(
                self.workspace_dir, 'aglivc_1.tif'),
            'aglive_1_1_path': os.path.join(
                self.workspace_dir, 'aglive_1_1.tif'),
            'aglive_2_1_path': os.path.join(
                self.workspace_dir, 'aglive_2_1.tif'),
            'stdedc_1_path': os.path.join(
                self.workspace_dir, 'stdedc_1.tif'),
            'stdede_1_1_path': os.path.join(
                self.workspace_dir, 'stdede_1_1.tif'),
            'stdede_2_1_path': os.path.join(
                self.workspace_dir, 'stdede_2_1.tif'),
            'minerl_1_1_path': os.path.join(
                self.workspace_dir, 'minerl_1_1.tif'),
            'minerl_1_2_path': os.path.join(
                self.workspace_dir, 'minerl_1_2.tif'),
            'metabc_1_path': os.path.join(
                self.workspace_dir, 'metabc.tif'),
            'strucc_1_path': os.path.join(
                self.workspace_dir, 'strucc.tif'),
            'struce_1_1_path': os.path.join(
                self.workspace_dir, 'struce_1_1.tif'),
            'metabe_1_1_path': os.path.join(
                self.workspace_dir, 'metabe_1_1.tif'),
            'struce_1_2_path': os.path.join(
                self.workspace_dir, 'struce_1_2.tif'),
            'metabe_1_2_path': os.path.join(
                self.workspace_dir, 'metabe_1_2.tif'),
            'strlig_1_path': os.path.join(self.workspace_dir, 'strlig.tif')
        }
        create_constant_raster(sv_reg['aglivc_1_path'], aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], aglive_1)
        create_constant_raster(sv_reg['aglive_2_1_path'], aglive_2)
        create_constant_raster(sv_reg['stdedc_1_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_1_path'], stdede_1)
        create_constant_raster(sv_reg['stdede_2_1_path'], stdede_2)
        create_constant_raster(sv_reg['minerl_1_1_path'], minerl_1_1)
        create_constant_raster(sv_reg['minerl_1_2_path'], minerl_1_2)
        create_constant_raster(sv_reg['metabc_1_path'], metabc_lyr)
        create_constant_raster(sv_reg['strucc_1_path'], strucc_lyr)
        create_constant_raster(sv_reg['struce_1_1_path'], struce_lyr_1)
        create_constant_raster(sv_reg['metabe_1_1_path'], metabe_lyr_1)
        create_constant_raster(sv_reg['struce_1_2_path'], struce_lyr_2)
        create_constant_raster(sv_reg['metabe_1_2_path'], metabe_lyr_2)
        create_constant_raster(sv_reg['strlig_1_path'], strlig_lyr)

        month_reg = {
            'flgrem_1': os.path.join(self.workspace_dir, 'flgrem_1.tif'),
            'fdgrem_1': os.path.join(self.workspace_dir, 'fdgrem_1.tif'),
        }
        create_constant_raster(month_reg['flgrem_1'], flgrem)
        create_constant_raster(month_reg['fdgrem_1'], fdgrem)

        animal_trait_table = {
            1: {
                'gfcret': gfcret,
                'gret_2': gret_2,
                'fecf_1': fecf_1,
                'fecf_2': fecf_2,
                'feclig': feclig,
            }
        }
        pft_id_set = [1]

        # known state variables after grazing
        aglivc_after = 6.163039
        stdedc_after = 4.062901
        aglive_1_after = 0.2865
        aglive_2_after = 0.00824278
        stdede_1_after = 0.159094
        stdede_2_after = 0.00542445
        minerl_1_1_after = 40.46379
        minerl_1_2_after = 24.189344
        metabc_1_after = 7.940992
        strucc_after = 158.04929
        metabe_1_1_after = 0.441906
        metabe_1_2_after = 0.0571507
        struce_1_1_after = 0.8049664
        struce_1_2_after = 0.315347
        strlig_1_after = 0.224322

        forage._grazing(
            aligned_inputs, site_param_table, month_reg, animal_trait_table,
            pft_id_set, sv_reg)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], aglivc_after - tolerance,
            aglivc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdedc_1_path'], stdedc_after - tolerance,
            stdedc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], aglive_1_after - tolerance,
            aglive_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], aglive_2_after - tolerance,
            aglive_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_1_1_path'], stdede_1_after - tolerance,
            stdede_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_2_1_path'], stdede_2_after - tolerance,
            stdede_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_1_path'], minerl_1_1_after - tolerance,
            minerl_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_2_path'], minerl_1_2_after - tolerance,
            minerl_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabc_1_path'], metabc_1_after - tolerance,
            metabc_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strucc_1_path'], strucc_after - tolerance,
            strucc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_1_path'], metabe_1_1_after - tolerance,
            metabe_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_2_path'], metabe_1_2_after - tolerance,
            metabe_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_1_path'], struce_1_1_after - tolerance,
            struce_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_2_path'], struce_1_2_after - tolerance,
            struce_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strlig_1_path'], strlig_1_after - tolerance,
            strlig_1_after + tolerance, _SV_NODATA)

        # known inputs: two pfts, 50% cover each
        aligned_inputs['pft_2'] = os.path.join(self.workspace_dir, 'pft_2.tif')
        create_constant_raster(aligned_inputs['pft_1'], 0.5)
        create_constant_raster(aligned_inputs['pft_2'], 0.5)

        sv_reg['aglivc_2_path'] = os.path.join(
            self.workspace_dir, 'aglivc_2.tif')
        sv_reg['aglive_1_2_path'] = os.path.join(
            self.workspace_dir, 'aglive_1_2.tif')
        sv_reg['aglive_2_2_path'] = os.path.join(
            self.workspace_dir, 'aglive_2_2.tif')
        sv_reg['stdedc_2_path'] = os.path.join(
            self.workspace_dir, 'stdedc_2.tif')
        sv_reg['stdede_1_2_path'] = os.path.join(
            self.workspace_dir, 'stdede_1_2.tif')
        sv_reg['stdede_2_2_path'] = os.path.join(
            self.workspace_dir, 'stdede_2_2.tif')
        create_constant_raster(sv_reg['aglivc_1_path'], aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], aglive_1)
        create_constant_raster(sv_reg['aglive_2_1_path'], aglive_2)
        create_constant_raster(sv_reg['stdedc_1_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_1_path'], stdede_1)
        create_constant_raster(sv_reg['stdede_2_1_path'], stdede_2)
        create_constant_raster(sv_reg['minerl_1_1_path'], minerl_1_1)
        create_constant_raster(sv_reg['minerl_1_2_path'], minerl_1_2)
        create_constant_raster(sv_reg['metabc_1_path'], metabc_lyr)
        create_constant_raster(sv_reg['strucc_1_path'], strucc_lyr)
        create_constant_raster(sv_reg['struce_1_1_path'], struce_lyr_1)
        create_constant_raster(sv_reg['metabe_1_1_path'], metabe_lyr_1)
        create_constant_raster(sv_reg['struce_1_2_path'], struce_lyr_2)
        create_constant_raster(sv_reg['metabe_1_2_path'], metabe_lyr_2)
        create_constant_raster(sv_reg['strlig_1_path'], strlig_lyr)
        create_constant_raster(sv_reg['aglivc_2_path'], aglivc)
        create_constant_raster(sv_reg['aglive_1_2_path'], aglive_1)
        create_constant_raster(sv_reg['aglive_2_2_path'], aglive_2)
        create_constant_raster(sv_reg['stdedc_2_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_2_path'], stdede_1)
        create_constant_raster(sv_reg['stdede_2_2_path'], stdede_2)

        month_reg['flgrem_2'] = os.path.join(
            self.workspace_dir, 'flgrem_2.tif')
        month_reg['fdgrem_2'] = os.path.join(
            self.workspace_dir, 'fdgrem_2.tif')
        create_constant_raster(month_reg['flgrem_2'], flgrem)
        create_constant_raster(month_reg['fdgrem_2'], fdgrem)

        pft_id_set = [1, 2]

        forage._grazing(
            aligned_inputs, site_param_table, month_reg, animal_trait_table,
            pft_id_set, sv_reg)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], aglivc_after - tolerance,
            aglivc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdedc_1_path'], stdedc_after - tolerance,
            stdedc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], aglive_1_after - tolerance,
            aglive_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], aglive_2_after - tolerance,
            aglive_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_1_1_path'], stdede_1_after - tolerance,
            stdede_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['stdede_2_1_path'], stdede_2_after - tolerance,
            stdede_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_1_path'], minerl_1_1_after - tolerance,
            minerl_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['minerl_1_2_path'], minerl_1_2_after - tolerance,
            minerl_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabc_1_path'], metabc_1_after - tolerance,
            metabc_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strucc_1_path'], strucc_after - tolerance,
            strucc_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_1_path'], metabe_1_1_after - tolerance,
            metabe_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['metabe_1_2_path'], metabe_1_2_after - tolerance,
            metabe_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_1_path'], struce_1_1_after - tolerance,
            struce_1_1_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['struce_1_2_path'], struce_1_2_after - tolerance,
            struce_1_2_after + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['strlig_1_path'], strlig_1_after - tolerance,
            strlig_1_after + tolerance, _SV_NODATA)

    def test_apply_new_growth(self):
        """Test `_apply_new_growth`.

        Use the function `_apply_new_growth` to update aboveground live biomass
        with new growth. Test that state variables are updated to values that
        match values calculated by hand.

        Raises:
            AssertionError if `_apply_new_growth` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known values
        pft_id_set = [1]
        initial_aglivc = 25.72
        initial_aglive_1 = 0.41
        initial_aglive_2 = 0.32

        delta_aglivc = 3.28
        delta_aglive_1 = 0.002
        delta_aglive_2 = 0.44

        mod_aglivc = initial_aglivc + delta_aglivc
        mod_aglive_1 = initial_aglive_1 + delta_aglive_1
        mod_aglive_2 = initial_aglive_2 + delta_aglive_2

        # raster-based inputs
        sv_reg = {
            'aglivc_1_path': os.path.join(self.workspace_dir, 'aglivc_1.tif'),
            'aglive_1_1_path': os.path.join(
                self.workspace_dir, 'aglive_1_1.tif'),
            'aglive_2_1_path': os.path.join(
                self.workspace_dir, 'aglive_2_1.tif'),
        }
        create_constant_raster(sv_reg['aglivc_1_path'], initial_aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], initial_aglive_1)
        create_constant_raster(sv_reg['aglive_2_1_path'], initial_aglive_2)

        delta_sv_dir = tempfile.mkdtemp(dir=self.workspace_dir)
        delta_agliv_dict = {
            'delta_aglivc_1': os.path.join(
                delta_sv_dir, 'delta_aglivc.tif'),
            'delta_aglive_1_1': os.path.join(
                delta_sv_dir, 'delta_aglive_1.tif'),
            'delta_aglive_2_1': os.path.join(
                delta_sv_dir, 'delta_aglive_2.tif'),
        }
        create_constant_raster(
            delta_agliv_dict['delta_aglivc_1'], delta_aglivc)
        create_constant_raster(
            delta_agliv_dict['delta_aglive_1_1'], delta_aglive_1)
        create_constant_raster(
            delta_agliv_dict['delta_aglive_2_1'], delta_aglive_2)

        forage._apply_new_growth(delta_agliv_dict, pft_id_set, sv_reg)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], mod_aglivc - tolerance,
            mod_aglivc + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], mod_aglive_1 - tolerance,
            mod_aglive_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], mod_aglive_2 - tolerance,
            mod_aglive_2 + tolerance, _SV_NODATA)

        create_constant_raster(sv_reg['aglivc_1_path'], initial_aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], initial_aglive_1)
        create_constant_raster(sv_reg['aglive_2_1_path'], initial_aglive_2)

        delta_sv_dir = tempfile.mkdtemp(dir=self.workspace_dir)
        delta_agliv_dict = {
            'delta_aglivc_1': os.path.join(
                delta_sv_dir, 'delta_aglivc.tif'),
            'delta_aglive_1_1': os.path.join(
                delta_sv_dir, 'delta_aglive_1.tif'),
            'delta_aglive_2_1': os.path.join(
                delta_sv_dir, 'delta_aglive_2.tif'),
        }
        create_constant_raster(
            delta_agliv_dict['delta_aglivc_1'], delta_aglivc)
        create_constant_raster(
            delta_agliv_dict['delta_aglive_1_1'], delta_aglive_1)
        create_constant_raster(
            delta_agliv_dict['delta_aglive_2_1'], delta_aglive_2)

        insert_nodata_values_into_raster(sv_reg['aglivc_1_path'], _SV_NODATA)
        insert_nodata_values_into_raster(sv_reg['aglive_1_1_path'], _SV_NODATA)
        insert_nodata_values_into_raster(sv_reg['aglive_2_1_path'], _SV_NODATA)
        insert_nodata_values_into_raster(
            delta_agliv_dict['delta_aglivc_1'], _SV_NODATA)
        insert_nodata_values_into_raster(
            delta_agliv_dict['delta_aglive_1_1'], _SV_NODATA)
        insert_nodata_values_into_raster(
            delta_agliv_dict['delta_aglive_2_1'], _SV_NODATA)

        forage._apply_new_growth(delta_agliv_dict, pft_id_set, sv_reg)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglivc_1_path'], mod_aglivc - tolerance,
            mod_aglivc + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_1_1_path'], mod_aglive_1 - tolerance,
            mod_aglive_1 + tolerance, _SV_NODATA)
        self.assert_all_values_in_raster_within_range(
            sv_reg['aglive_2_1_path'], mod_aglive_2 - tolerance,
            mod_aglive_2 + tolerance, _SV_NODATA)

    def test_nonspatial_derived_animal_traits(self):
        """Test calculation of nonspatial derived animal traits.

        Use the function `calc_derived_animal_traits` to populate the animal
        trait table with fixed parameters from Freer et al. (2012) and derived
        animal traits. Test the derived animal traits against values calculated
        by hand. Use the function `update_breeding_female_status` to update the
        reproductive status of breeding females. Use the function
        `calc_max_intake` to calculate maximum potential intake.

        Raises:
            AssertionError if derived animal traits calculated by
            `calc_derived_animal_traits` do not match values calculated by
            hand.
            AssertionError if the reproductive status of breeding females is
            not correctly updated according to model step.
            AssertionError if `calc_max_intake` does not match values
            calculated by hand.

        Returns:
            None

        """
        # Freer parameters stored as constants in forage.py
        _FREER_PARAM_DICT = {
            'b_indicus': {
                'CN1': 0.0115,
                'CN2': 0.27,
                'CN3': 0.4,
                'CI1': 0.025,
                'CI2': 1.7,
                'CI3': 0.22,
                'CI4': 60,
                'CI5': 0.01,
                'CI6': 25,
                'CI7': 22,
                'CI8': 62,
                'CI9': 1.7,
                'CI10': 0.6,
                'CI11': 0.05,
                'CI12': 0.15,
                'CI13': 0.005,
                'CI14': 0.002,
                'CI15': 0.5,
                'CI19': 0.416,
                'CI20': 1.5,
                'CR1': 0.8,
                'CR2': 0.17,
                'CR3': 1.7,
                'CR4': 0.00078,
                'CR5': 0.6,
                'CR6': 0.00074,
                'CR7': 0.5,
                'CR11': 10.5,
                'CR12': 0.8,
                'CR13': 0.35,
                'CR14': 1,
                'CR20': 11.5,
                'CK1': 0.5,
                'CK2': 0.02,
                'CK3': 0.85,
                'CK5': 0.4,
                'CK6': 0.02,
                'CK8': 0.133,
                'CK10': 0.84,
                'CK11': 0.8,
                'CK13': 0.035,
                'CK14': 0.33,
                'CK15': 0.12,
                'CK16': 0.043,
                'CL0': 0.375,
                'CL1': 4,
                'CL2': 30,
                'CL3': 0.6,
                'CL4': 0.6,
                'CL5': 0.94,
                'CL6': 3.1,
                'CL7': 1.17,
                'CL15': 0.032,
                'CL16': 0.7,
                'CL17': 0.01,
                'CL19': 1.6,
                'CL20': 4,
                'CL21': 0.004,
                'CL22': 0.006,
                'CL23': 3,
                'CL24': 0.6,
                'CM1': 0.09,
                'CM2': 0.31,
                'CM3': 0.00008,
                'CM4': 0.84,
                'CM5': 0.23,
                'CM6': 0.0025,
                'CM7': 0.9,
                'CM8': 0.000057,
                'CM9': 0.16,
                'CM10': 0.0152,
                'CM11': 0.000526,
                'CM12': 0.0129,
                'CM13': 0.0338,
                'CM14': 0.00011,
                'CM15': 1.15,
                'CM16': 0.0026,
                'CM17': 5,
                'CRD1': 0.3,
                'CRD2': 0.25,
                'CRD3': 0.1,
                'CRD4': 0.007,
                'CRD5': 0.005,
                'CRD6': 0.35,
                'CRD7': 0.1,
                'CA1': 0.05,
                'CA2': 0.85,
                'CA3': 5.5,
                'CA4': 0.178,
                'CA6': 1,
                'CA7': 0.6,
                'CG1': 1,
                'CG2': 0.7,
                'CG4': 6,
                'CG5': 0.4,
                'CG6': 0.9,
                'CG7': 0.97,
                'CG8': 23.2,
                'CG9': 16.5,
                'CG10': 2,
                'CG11': 13.8,
                'CG12': 0.092,
                'CG13': 0.12,
                'CG14': 0.008,
                'CG15': 0.115,
                'CP1': 285,
                'CP2': 2.2,
                'CP3': 1.77,
                'CP4': 0.33,
                'CP5': 1.8,
                'CP6': 2.42,
                'CP7': 1.16,
                'CP8': 4.11,
                'CP9': 343.5,
                'CP10': 0.0164,
                'CP11': 0.134,
                'CP12': 6.22,
                'CP13': 0.747,
                'CP14': 1,
                'CP15': 0.07,
            },
            'b_taurus': {
                'CN1': 0.0115,
                'CN2': 0.27,
                'CN3': 0.4,
                'CI1': 0.025,
                'CI2': 1.7,
                'CI3': 0.22,
                'CI4': 60,
                'CI5': 0.02,
                'CI6': 25,
                'CI7': 22,
                'CI8': 62,
                'CI9': 1.7,
                'CI10': 0.6,
                'CI11': 0.05,
                'CI12': 0.15,
                'CI13': 0.005,
                'CI14': 0.002,
                'CI15': 0.5,
                'CI19': 0.416,
                'CI20': 1.5,
                'CR1': 0.8,
                'CR2': 0.17,
                'CR3': 1.7,
                'CR4': 0.00078,
                'CR5': 0.6,
                'CR6': 0.00074,
                'CR7': 0.5,
                'CR11': 10.5,
                'CR12': 0.8,
                'CR13': 0.35,
                'CR14': 1,
                'CR20': 11.5,
                'CK1': 0.5,
                'CK2': 0.02,
                'CK3': 0.85,
                'CK5': 0.4,
                'CK6': 0.02,
                'CK8': 0.133,
                'CK10': 0.84,
                'CK11': 0.8,
                'CK13': 0.035,
                'CK14': 0.33,
                'CK15': 0.12,
                'CK16': 0.043,
                'CL0': 0.375,
                'CL1': 4,
                'CL2': 30,
                'CL3': 0.6,
                'CL4': 0.6,
                'CL5': 0.94,
                'CL6': 3.1,
                'CL7': 1.17,
                'CL15': 0.032,
                'CL16': 0.7,
                'CL17': 0.01,
                'CL19': 1.6,
                'CL20': 4,
                'CL21': 0.004,
                'CL22': 0.006,
                'CL23': 3,
                'CL24': 0.6,
                'CM1': 0.09,
                'CM2': 0.36,
                'CM3': 0.00008,
                'CM4': 0.84,
                'CM5': 0.23,
                'CM6': 0.0025,
                'CM7': 0.9,
                'CM8': 0.000057,
                'CM9': 0.16,
                'CM10': 0.0152,
                'CM11': 0.000526,
                'CM12': 0.0161,
                'CM13': 0.0422,
                'CM14': 0.00011,
                'CM15': 1.15,
                'CM16': 0.0026,
                'CM17': 5,
                'CRD1': 0.3,
                'CRD2': 0.25,
                'CRD3': 0.1,
                'CRD4': 0.007,
                'CRD5': 0.005,
                'CRD6': 0.35,
                'CRD7': 0.1,
                'CA1': 0.05,
                'CA2': 0.85,
                'CA3': 5.5,
                'CA4': 0.178,
                'CA6': 1,
                'CA7': 0.6,
                'CG1': 1,
                'CG2': 0.7,
                'CG4': 6,
                'CG5': 0.4,
                'CG6': 0.9,
                'CG7': 0.97,
                'CG8': 27,
                'CG9': 20.3,
                'CG10': 2,
                'CG11': 13.8,
                'CG12': 0.072,
                'CG13': 0.14,
                'CG14': 0.008,
                'CG15': 0.115,
                'CP1': 285,
                'CP2': 2.2,
                'CP3': 1.77,
                'CP4': 0.33,
                'CP5': 1.8,
                'CP6': 2.42,
                'CP7': 1.16,
                'CP8': 4.11,
                'CP9': 343.5,
                'CP10': 0.0164,
                'CP11': 0.134,
                'CP12': 6.22,
                'CP13': 0.747,
                'CP14': 1,
                'CP15': 0.07,
            },
            'indicus_x_taurus': {
                'CN1': 0.0115,
                'CN2': 0.27,
                'CN3': 0.4,
                'CI1': 0.025,
                'CI2': 1.7,
                'CI3': 0.22,
                'CI4': 60,
                'CI5': 0.015,
                'CI6': 25,
                'CI7': 22,
                'CI8': 62,
                'CI9': 1.7,
                'CI10': 0.6,
                'CI11': 0.05,
                'CI12': 0.15,
                'CI13': 0.005,
                'CI14': 0.002,
                'CI15': 0.5,
                'CI19': 0.416,
                'CI20': 1.5,
                'CR1': 0.8,
                'CR2': 0.17,
                'CR3': 1.7,
                'CR4': 0.00078,
                'CR5': 0.6,
                'CR6': 0.00074,
                'CR7': 0.5,
                'CR11': 10.5,
                'CR12': 0.8,
                'CR13': 0.35,
                'CR14': 1,
                'CR20': 11.5,
                'CK1': 0.5,
                'CK2': 0.02,
                'CK3': 0.85,
                'CK5': 0.4,
                'CK6': 0.02,
                'CK8': 0.133,
                'CK10': 0.84,
                'CK11': 0.8,
                'CK13': 0.035,
                'CK14': 0.33,
                'CK15': 0.12,
                'CK16': 0.043,
                'CL0': 0.375,
                'CL1': 4,
                'CL2': 30,
                'CL3': 0.6,
                'CL4': 0.6,
                'CL5': 0.94,
                'CL6': 3.1,
                'CL7': 1.17,
                'CL15': 0.032,
                'CL16': 0.7,
                'CL17': 0.01,
                'CL19': 1.6,
                'CL20': 4,
                'CL21': 0.004,
                'CL22': 0.006,
                'CL23': 3,
                'CL24': 0.6,
                'CM1': 0.09,
                'CM2': 0.335,
                'CM3': 0.00008,
                'CM4': 0.84,
                'CM5': 0.23,
                'CM6': 0.0025,
                'CM7': 0.9,
                'CM8': 0.000057,
                'CM9': 0.16,
                'CM10': 0.0152,
                'CM11': 0.000526,
                'CM12': 0.0145,
                'CM13': 0.038,
                'CM14': 0.00011,
                'CM15': 1.15,
                'CM16': 0.0026,
                'CM17': 5,
                'CRD1': 0.3,
                'CRD2': 0.25,
                'CRD3': 0.1,
                'CRD4': 0.007,
                'CRD5': 0.005,
                'CRD6': 0.35,
                'CRD7': 0.1,
                'CA1': 0.05,
                'CA2': 0.85,
                'CA3': 5.5,
                'CA4': 0.178,
                'CA6': 1,
                'CA7': 0.6,
                'CG1': 1,
                'CG2': 0.7,
                'CG4': 6,
                'CG5': 0.4,
                'CG6': 0.9,
                'CG7': 0.97,
                'CG8': 27,
                'CG9': 20.3,
                'CG10': 2,
                'CG11': 13.8,
                'CG12': 0.072,
                'CG13': 0.14,
                'CG14': 0.008,
                'CG15': 0.115,
                'CP1': 285,
                'CP2': 2.2,
                'CP3': 1.77,
                'CP4': 0.33,
                'CP5': 1.8,
                'CP6': 2.42,
                'CP7': 1.16,
                'CP8': 4.11,
                'CP9': 343.5,
                'CP10': 0.0164,
                'CP11': 0.134,
                'CP12': 6.22,
                'CP13': 0.747,
                'CP14': 1,
                'CP15': 0.07,
            },
            'sheep': {
                'CN1': 0.0157,
                'CN2': 0.27,
                'CN3': 0.4,
                'CI1': 0.04,
                'CI2': 1.7,
                'CI3': 0.5,
                'CI4': 25,
                'CI5': 0.01,
                'CI6': 25,
                'CI7': 22,
                'CI8': 28,
                'CI9': 1.4,
                'CI12': 0.15,
                'CI13': 0.02,
                'CI14': 0.002,
                'CI20': 1.5,
                'CR1': 0.8,
                'CR2': 0.17,
                'CR3': 1.7,
                'CR4': 0.00112,
                'CR5': 0.6,
                'CR6': 0.00112,
                'CR7': 0,
                'CR11': 10.5,
                'CR12': 0.8,
                'CR13': 0.35,
                'CR14': 1,
                'CR20': 11.5,
                'CK1': 0.5,
                'CK2': 0.02,
                'CK3': 0.85,
                'CK5': 0.4,
                'CK6': 0.02,
                'CK8': 0.133,
                'CK10': 0.84,
                'CK11': 0.8,
                'CK13': 0.035,
                'CK14': 0.33,
                'CK15': 0.12,
                'CK16': 0.043,
                'CL0': 0.486,
                'CL1': 2,
                'CL2': 22,
                'CL3': 1,
                'CL5': 0.94,
                'CL6': 4.7,
                'CL7': 1.17,
                'CL15': 0.045,
                'CL16': 0.7,
                'CL17': 0.01,
                'CL19': 1.6,
                'CL20': 4,
                'CL21': 0.008,
                'CL22': 0.012,
                'CL23': 3,
                'CL24': 0.6,
                'CM1': 0.09,
                'CM2': 0.26,
                'CM3': 0.00008,
                'CM4': 0.84,
                'CM5': 0.23,
                'CM6': 0.02,
                'CM7': 0.9,
                'CM8': 0.000057,
                'CM9': 0.16,
                'CM10': 0.0152,
                'CM11': 0.00046,
                'CM12': 0.000147,
                'CM13': 0.003375,
                'CM15': 1.15,
                'CM16': 0.0026,
                'CM17': 40,
                'CRD1': 0.3,
                'CRD2': 0.25,
                'CRD3': 0.1,
                'CRD4': 0.007,
                'CRD5': 0.005,
                'CRD6': 0.35,
                'CRD7': 0.1,
                'CA1': 0.05,
                'CA2': 0.85,
                'CA3': 5.5,
                'CA4': 0.178,
                'CA6': 1,
                'CA7': 0.6,
                'CG1': 0.6,
                'CG2': 0.7,
                'CG4': 6,
                'CG5': 0.4,
                'CG6': 0.9,
                'CG7': 0.97,
                'CG8': 27,
                'CG9': 20.3,
                'CG10': 2,
                'CG11': 13.8,
                'CG12': 0.072,
                'CG13': 0.14,
                'CG14': 0.008,
                'CG15': 0.115,
                'CW1': 24,
                'CW2': 0.004,
                'CW3': 0.7,
                'CW5': 0.25,
                'CW6': 0.072,
                'CW7': 1.35,
                'CW8': 0.016,
                'CW9': 1,
                'CW12': 0.025,
                'CP1': 150,
                'CP2': 1.304,
                'CP3': 2.625,
                'CP4': 0.33,
                'CP5': 1.43,
                'CP6': 3.38,
                'CP7': 0.91,
                'CP8': 4.33,
                'CP9': 4.37,
                'CP10': 0.965,
                'CP11': 0.145,
                'CP12': 4.56,
                'CP13': 0.9,
                'CP14': 1.5,
                'CP15': 0.1,
            },
        }
        from rangeland_production import forage
        from rangeland_production import utils

        # known derived trait values
        entire_m_Z = 0.480537
        castrate_Z = 0.394308
        heifer_Z = 0.421794
        sheep_Z = 0.562727

        entire_m_ZF = 1.019463
        castrate_ZF = 1.105692
        heifer_ZF = 1.078206
        sheep_ZF = 1.

        entire_m_BC = 0.998350
        castrate_BC = 0.995369
        heifer_BC = 0.998655
        sheep_BC = 1.020165

        args = foragetests.generate_base_args(self.workspace_dir)
        freer_parameter_df = pandas.DataFrame.from_dict(
            _FREER_PARAM_DICT, orient='index')
        freer_parameter_df['type'] = freer_parameter_df.index
        input_animal_trait_table = utils.build_lookup_from_csv(
            args['animal_trait_path'], 'animal_id')
        animal_trait_table = forage.calc_derived_animal_traits(
            input_animal_trait_table, freer_parameter_df)

        self.assertAlmostEqual(
            animal_trait_table[1]['Z'], entire_m_Z, places=6)
        self.assertAlmostEqual(
            animal_trait_table[3]['Z'], castrate_Z, places=6)
        self.assertAlmostEqual(
            animal_trait_table[4]['Z'], heifer_Z, places=6)
        self.assertAlmostEqual(
            animal_trait_table[0]['Z'], sheep_Z, places=6)

        self.assertAlmostEqual(
            animal_trait_table[1]['ZF'], entire_m_ZF, places=6)
        self.assertAlmostEqual(
            animal_trait_table[3]['ZF'], castrate_ZF, places=6)
        self.assertAlmostEqual(
            animal_trait_table[4]['ZF'], heifer_ZF, places=6)
        self.assertAlmostEqual(
            animal_trait_table[0]['ZF'], sheep_ZF, places=6)

        self.assertAlmostEqual(
            animal_trait_table[1]['BC'], entire_m_BC, places=6)
        self.assertAlmostEqual(
            animal_trait_table[3]['BC'], castrate_BC, places=6)
        self.assertAlmostEqual(
            animal_trait_table[4]['BC'], heifer_BC, places=6)
        self.assertAlmostEqual(
            animal_trait_table[0]['BC'], sheep_BC, places=6)

        # Test updating reproductive status of breeding females.
        # model step indicates pregnancy
        month_index = 2
        for animal_id in animal_trait_table.keys():
            if animal_trait_table[animal_id]['sex'] == 'breeding_female':
                revised_animal_dict = forage.update_breeding_female_status(
                    animal_trait_table[animal_id], month_index)
                animal_trait_table[animal_id] = revised_animal_dict
        # assert that reproductive status of breeding females is correct
        self.assertEqual(
            animal_trait_table[2]['reproductive_status_int'], 1)
        # assert that reproductive status of all other animal types is 0
        for animal_id in [0, 1, 3, 4]:
            self.assertEqual(
                animal_trait_table[animal_id]['reproductive_status_int'], 0)

        # model step indicates lactating
        month_index = 6
        for animal_id in animal_trait_table.keys():
            if animal_trait_table[animal_id]['sex'] == 'breeding_female':
                revised_animal_dict = forage.update_breeding_female_status(
                    animal_trait_table[animal_id], month_index)
                animal_trait_table[animal_id] = revised_animal_dict
        # assert that reproductive status of breeding females is correct
        self.assertEqual(
            animal_trait_table[2]['reproductive_status_int'], 2)
        # assert that reproductive status of all other animal types is 0
        for animal_id in [0, 1, 3, 4]:
            self.assertEqual(
                animal_trait_table[animal_id]['reproductive_status_int'], 0)

        # model step indicates open
        month_index = 8
        for animal_id in animal_trait_table.keys():
            if animal_trait_table[animal_id]['sex'] == 'breeding_female':
                revised_animal_dict = forage.update_breeding_female_status(
                    animal_trait_table[animal_id], month_index)
                animal_trait_table[animal_id] = revised_animal_dict
        self.assertEqual(
            animal_trait_table[2]['reproductive_status_int'], 0)
        # assert that reproductive status of all other animal types is 0
        for animal_id in [0, 1, 3, 4]:
            self.assertEqual(
                animal_trait_table[animal_id]['reproductive_status_int'], 0)

        # Test calculating maximum intake.
        # known values calculated by hand
        entire_m_max_intake = 12.3674657
        castrate_max_intake = 9.3135440
        heifer_max_intake = 8.1275358
        sheep_max_intake = 0.8120074

        for animal_id in animal_trait_table.keys():
            revised_animal_trait_dict = forage.calc_max_intake(
                animal_trait_table[animal_id])
            animal_trait_table[animal_id] = revised_animal_trait_dict
        self.assertAlmostEqual(
            animal_trait_table[1]['max_intake'], entire_m_max_intake)
        self.assertAlmostEqual(
            animal_trait_table[3]['max_intake'], castrate_max_intake)
        self.assertAlmostEqual(
            animal_trait_table[4]['max_intake'], heifer_max_intake)
        self.assertAlmostEqual(
            animal_trait_table[0]['max_intake'], sheep_max_intake)

    def test_calc_pasture_height(self):
        """Test `calc_pasture_height`.

        Use the function `calc_pasture_height` to estimate the height of each
        feed type from its biomass. Test that the function matches values
        calculated by hand.

        Raises:
            AssertionError if `calc_pasture_height` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known inputs
        aglivc_4 = 80
        stdedc_4 = 45
        cover_4 = 0.5
        aglivc_5 = 99
        stdedc_5 = 36
        cover_5 = 0.3

        height_agliv_4 = 10.2503075704191
        height_dead_4 = 5.76579800836076
        height_agliv_5 = 7.61085337103621
        height_dead_5 = 2.76758304401317

        # raster-based inputs
        sv_reg = {
            'aglivc_4_path': os.path.join(self.workspace_dir, 'aglivc_4.tif'),
            'stdedc_4_path': os.path.join(self.workspace_dir, 'stdedc_4.tif'),
            'aglivc_5_path': os.path.join(self.workspace_dir, 'aglivc_5.tif'),
            'stdedc_5_path': os.path.join(self.workspace_dir, 'stdedc_5.tif'),
        }
        create_constant_raster(sv_reg['aglivc_4_path'], aglivc_4)
        create_constant_raster(sv_reg['stdedc_4_path'], stdedc_4)
        create_constant_raster(sv_reg['aglivc_5_path'], aglivc_5)
        create_constant_raster(sv_reg['stdedc_5_path'], stdedc_5)
        aligned_inputs = {
            'pft_4': os.path.join(self.workspace_dir, 'cover_4.tif'),
            'pft_5': os.path.join(self.workspace_dir, 'cover_5.tif'),
        }
        create_constant_raster(aligned_inputs['pft_4'], cover_4)
        create_constant_raster(aligned_inputs['pft_5'], cover_5)
        pft_id_set = [4, 5]
        processing_dir = self.workspace_dir

        pasture_height_dict = forage.calc_pasture_height(
            sv_reg, aligned_inputs, pft_id_set, processing_dir)

        self.assert_all_values_in_raster_within_range(
            pasture_height_dict['agliv_4'], height_agliv_4 - tolerance,
            height_agliv_4 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            pasture_height_dict['stded_4'], height_dead_4 - tolerance,
            height_dead_4 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            pasture_height_dict['agliv_5'], height_agliv_5 - tolerance,
            height_agliv_5 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            pasture_height_dict['stded_5'], height_dead_5 - tolerance,
            height_dead_5 + tolerance, _TARGET_NODATA)

    def test_calc_fraction_biomass(self):
        """Test `calc_fraction_biomass`.

        Use the function `calc_fraction_biomass` to calculate the relative
        proportion of biomass represented by each feed type. Test that the
        results match values calculated by hand.

        Raises:
            AssertionError if `calc_fraction_biomass` does not match values
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known inputs
        aglivc_4 = 80
        stdedc_4 = 45
        cover_4 = 0.5
        aglivc_5 = 99
        stdedc_5 = 36
        cover_5 = 0.3
        total_weighted_C = 103

        agliv_frac_bio_4 = 0.38835
        stded_frac_bio_4 = 0.21845
        agliv_frac_bio_5 = 0.28835
        stded_frac_bio_5 = 0.10485

        # raster-based inputs
        sv_reg = {
            'aglivc_4_path': os.path.join(self.workspace_dir, 'aglivc_4.tif'),
            'stdedc_4_path': os.path.join(self.workspace_dir, 'stdedc_4.tif'),
            'aglivc_5_path': os.path.join(self.workspace_dir, 'aglivc_5.tif'),
            'stdedc_5_path': os.path.join(self.workspace_dir, 'stdedc_5.tif'),
        }
        create_constant_raster(sv_reg['aglivc_4_path'], aglivc_4)
        create_constant_raster(sv_reg['stdedc_4_path'], stdedc_4)
        create_constant_raster(sv_reg['aglivc_5_path'], aglivc_5)
        create_constant_raster(sv_reg['stdedc_5_path'], stdedc_5)
        aligned_inputs = {
            'pft_4': os.path.join(self.workspace_dir, 'cover_4.tif'),
            'pft_5': os.path.join(self.workspace_dir, 'cover_5.tif'),
        }
        create_constant_raster(aligned_inputs['pft_4'], cover_4)
        create_constant_raster(aligned_inputs['pft_5'], cover_5)
        total_weighted_C_path = os.path.join(
            self.workspace_dir, 'total_weighted_C.tif')
        create_constant_raster(total_weighted_C_path, total_weighted_C)
        pft_id_set = [4, 5]
        processing_dir = self.workspace_dir

        frac_biomass_dict = forage.calc_fraction_biomass(
            sv_reg, aligned_inputs, pft_id_set, processing_dir,
            total_weighted_C_path)

        self.assert_all_values_in_raster_within_range(
            frac_biomass_dict['agliv_4'], agliv_frac_bio_4 - tolerance,
            agliv_frac_bio_4 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            frac_biomass_dict['stded_4'], stded_frac_bio_4 - tolerance,
            stded_frac_bio_4 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            frac_biomass_dict['agliv_5'], agliv_frac_bio_5 - tolerance,
            agliv_frac_bio_5 + tolerance, _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            frac_biomass_dict['stded_5'], stded_frac_bio_5 - tolerance,
            stded_frac_bio_5 + tolerance, _TARGET_NODATA)

    def test_order_by_digestibility(self):
        """Test `order_by_digestibility`.

        Use the function `order_by_digestibility` to calculate the order of
        feed types according to their digestibility. Ensure that the order of
        feed types matches the order calculated by hand.

        Raises:
            AssertionError if `order_by_digestibility` does not match order
                calculated by hand

        Returns:
            None

        """
        from rangeland_production import forage

        # known inputs
        aglivc_4 = 80
        aglive_1_4 = 35
        stdedc_4 = 45
        stdede_1_4 = 12.3
        aglivc_5 = 99
        aglive_1_5 = 8.2
        stdedc_5 = 36
        stdede_1_5 = 22.5

        digestibility_order = ['stded_5', 'agliv_4', 'stded_4', 'agliv_5']

        # raster-based inputs
        sv_reg = {
            'aglivc_4_path': os.path.join(self.workspace_dir, 'aglivc_4.tif'),
            'aglive_1_4_path': os.path.join(
                self.workspace_dir, 'aglive_1_4.tif'),
            'stdedc_4_path': os.path.join(self.workspace_dir, 'stdedc_4.tif'),
            'stdede_1_4_path': os.path.join(
                self.workspace_dir, 'stdede_1_4.tif'),
            'aglivc_5_path': os.path.join(self.workspace_dir, 'aglivc_5.tif'),
            'aglive_1_5_path': os.path.join(
                self.workspace_dir, 'aglive_1_5.tif'),
            'stdedc_5_path': os.path.join(self.workspace_dir, 'stdedc_5.tif'),
            'stdede_1_5_path': os.path.join(
                self.workspace_dir, 'stdede_1_5.tif'),
        }
        args = foragetests.generate_base_args(self.workspace_dir)
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['aglivc_4_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[aglivc_4])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['aglive_1_4_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[aglive_1_4])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['stdedc_4_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[stdedc_4])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['stdede_1_4_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[stdede_1_4])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['aglivc_5_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[aglivc_5])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['aglive_1_5_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[aglive_1_5])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['aglivc_4_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[aglivc_4])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['stdedc_5_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[stdedc_5])
        pygeoprocessing.new_raster_from_base(
            args['site_param_spatial_index_path'], sv_reg['stdede_1_5_path'],
            gdal.GDT_Int32, [_TARGET_NODATA], fill_value_list=[stdede_1_5])
        pft_id_set = [4, 5]

        ordered_feed_types = forage.order_by_digestibility(
            sv_reg, pft_id_set, args['aoi_path'])

        self.assert_sorted_lists_equal(ordered_feed_types, digestibility_order)

    def test_calc_grazing_offtake(self):
        """Test `_calc_grazing_offtake.`

        Use the function `_calc_grazing_offtake` to perform diet selection from
        available forage. Ensure that the selected diet matches the results
        of diet selection performed by the beta rangeland model.

        Raises:
            AssertionError if `_calc_grazing_offtake` does not match diet
                selection results of the beta rangeland model

        Returns:
            None

        """
        from rangeland_production import forage
        tolerance = 0.00001

        # known inputs
        aglivc = 0.426
        aglive_1 = 0.0187
        stdedc = 11.2257
        stdede_1 = 0.4238
        stocking_density = 0.1
        proportion_legume = 0

        age = 116
        sex_int = 4
        type_int = 4
        W_total = 18.6
        max_intake = 0.8120073
        ZF = 1.
        CR1 = 0.8
        CR2 = 0.17
        CR3 = 1.7
        CR4 = 0.00112
        CR5 = 0.6
        CR6 = 0.00112
        CR12 = 0.8
        CR13 = 0.35
        CK1 = 0.5
        CK2 = 0.02
        CM1 = 0.09
        CM2 = 0.26
        CM3 = 0.00008
        CM4 = 0.84
        CM6 = 0.02
        CM7 = 0.9
        CM16 = 0.0026
        CRD1 = 0.3
        CRD2 = 0.25
        CRD4 = 0.007
        CRD5 = 0.005
        CRD6 = 0.35
        CRD7 = 0.1

        species_factor = 0
        digestibility_slope = 1.5349
        digestibility_intercept = 0.4147
        current_month = 4

        # spatial inputs
        aligned_inputs = {
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'proportion_legume_path': os.path.join(
                self.workspace_dir, 'proportion_legume.tif'),
        }
        create_constant_raster(aligned_inputs['pft_1'], 1)
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(
            aligned_inputs['proportion_legume_path'], proportion_legume)
        aoi_path = TEST_AOI
        sv_reg = {
            'aglivc_1_path': os.path.join(self.workspace_dir, 'aglivc.tif'),
            'aglive_1_1_path': os.path.join(self.workspace_dir, 'aglive.tif'),
            'stdedc_1_path': os.path.join(self.workspace_dir, 'stdedc.tif'),
            'stdede_1_1_path': os.path.join(self.workspace_dir, 'stdede.tif'),
        }
        create_constant_raster(sv_reg['aglivc_1_path'], aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], aglive_1)
        create_constant_raster(sv_reg['stdedc_1_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_1_path'], stdede_1)

        pft_id_set = [1]
        animal_index_path = os.path.join(self.workspace_dir, 'animal.tif')
        create_constant_raster(animal_index_path, 1)
        animal_trait_table = {
            1: {
                'age': age,
                'sex_int': sex_int,
                'type_int': type_int,
                'W_total': W_total,
                'max_intake': max_intake,
                'ZF': ZF,
                'CR1': CR1,
                'CR2': CR2,
                'CR3': CR3,
                'CR4': CR4,
                'CR5': CR5,
                'CR6': CR6,
                'CR12': CR12,
                'CR13': CR13,
                'CK1': CK1,
                'CK2': CK2,
                'CM1': CM1,
                'CM2': CM2,
                'CM3': CM3,
                'CM4': CM4,
                'CM6': CM6,
                'CM7': CM7,
                'CM16': CM16,
                'CRD1': CRD1,
                'CRD2': CRD2,
                'CRD4': CRD4,
                'CRD5': CRD5,
                'CRD6': CRD6,
                'CRD7': CRD7,
            }
        }
        veg_trait_table = {
            1: {
                'species_factor': species_factor,
                'digestibility_intercept': digestibility_intercept,
                'digestibility_slope': digestibility_slope,
            }
        }
        month_reg = {
            'animal_density': os.path.join(
                self.workspace_dir, 'animal_density.tif'),
            'flgrem_1': os.path.join(self.workspace_dir, 'flgrem_1.tif'),
            'fdgrem_1': os.path.join(self.workspace_dir, 'fdgrem_1.tif'),
        }
        create_constant_raster(month_reg['animal_density'], stocking_density)

        # management threshold does not restrict offtake
        management_threshold = 0.1
        forage._calc_grazing_offtake(
            aligned_inputs, aoi_path, management_threshold, sv_reg, pft_id_set,
            animal_index_path, animal_trait_table, veg_trait_table,
            current_month, month_reg)
        flgrem = 0.000643
        fdgrem = 0.002561

        self.assert_all_values_in_raster_within_range(
            month_reg['flgrem_1'], flgrem - tolerance, flgrem + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            month_reg['fdgrem_1'], fdgrem - tolerance, fdgrem + tolerance,
            _TARGET_NODATA)

        # management threshold restricts offtake
        management_threshold = 300
        forage._calc_grazing_offtake(
            aligned_inputs, aoi_path, management_threshold, sv_reg, pft_id_set,
            animal_index_path, animal_trait_table, veg_trait_table,
            current_month, month_reg)
        flgrem = 0
        fdgrem = 0

        self.assert_all_values_in_raster_within_range(
            month_reg['flgrem_1'], flgrem - tolerance, flgrem + tolerance,
            _TARGET_NODATA)
        self.assert_all_values_in_raster_within_range(
            month_reg['fdgrem_1'], fdgrem - tolerance, fdgrem + tolerance,
            _TARGET_NODATA)

    def test_animal_diet_sufficiency(self):
        """Test `_animal_diet_sufficiency`.

        Use the function `_animal_diet_sufficiency` to calculate the energy
        content of forage offtake and compare it to energy requirements of
        grazing animals. Ensure that estimated diet sufficiency matches the
        result of the beta rangeland model.

        Raises:
            AssertionError if `_animal_diet_sufficiency` does not match results
                of the beta rangeland model

        """
        from rangeland_production import forage
        tolerance = 0.000001

        # known inputs
        aglivc = 0.426
        aglive_1 = 0.0187
        stdedc = 11.2257
        stdede_1 = 0.4238
        stocking_density = 0.1

        animal_type = 4
        reproductive_status = 0
        SRW = 32.4
        SFW = 2.28
        age = 116
        sex_int = 4
        W_total = 18.6
        CK1 = 0.5
        CK2 = 0.02
        CM1 = 0.09
        CM2 = 0.26
        CM3 = 0.00008
        CM4 = 0.84
        CM6 = 0.02
        CM7 = 0.9
        CM16 = 0.0026
        CRD4 = 0.007
        CRD5 = 0.005
        CRD6 = 0.35
        CRD7 = 0.1
        Z = 0.562727
        BC = 1.020165
        A_foet = 0
        A_y = 0
        CK5 = 0.4
        CK6 = 0.02
        CK8 = 0.133
        CP1 = 150
        CP4 = 0.33
        CP5 = 1.43
        CP8 = 4.33
        CP9 = 4.37
        CP10 = 0.965
        CP15 = 0.1
        CL0 = 0.486
        CL1 = 2
        CL2 = 22
        CL3 = 1
        CL5 = 0.94
        CL6 = 4.7
        CL15 = 0.045
        CA1 = 0.05
        CA2 = 0.85
        CA3 = 5.5
        CA4 = 0.178
        CA6 = 1
        CA7 = 0.6
        CW1 = 24
        CW2 = 0.004
        CW3 = 0.7
        CW5 = 0.25
        CW6 = 0.072
        CW7 = 1.35
        CW8 = 0.016
        CW9 = 1
        CW12 = 0.025

        digestibility_slope = 1.5349
        digestibility_intercept = 0.4147
        current_month = 4

        flgrem = 0.000643
        fdgrem = 0.002561

        # raster-based inputs
        sv_reg = {
            'aglivc_1_path': os.path.join(self.workspace_dir, 'aglivc.tif'),
            'aglive_1_1_path': os.path.join(self.workspace_dir, 'aglive.tif'),
            'stdedc_1_path': os.path.join(self.workspace_dir, 'stdedc.tif'),
            'stdede_1_1_path': os.path.join(self.workspace_dir, 'stdede.tif'),
        }
        create_constant_raster(sv_reg['aglivc_1_path'], aglivc)
        create_constant_raster(sv_reg['aglive_1_1_path'], aglive_1)
        create_constant_raster(sv_reg['stdedc_1_path'], stdedc)
        create_constant_raster(sv_reg['stdede_1_1_path'], stdede_1)

        pft_id_set = [1]
        aligned_inputs = {
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
            'animal_index': os.path.join(self.workspace_dir, 'animal.tif'),
        }
        create_constant_raster(aligned_inputs['pft_1'], 1)
        create_constant_raster(aligned_inputs['animal_index'], 1)
        animal_trait_table = {
            1: {
                'type_int': animal_type,
                'reproductive_status_int': reproductive_status,
                'SRW_modified': SRW,
                'sfw': SFW,
                'age': age,
                'sex_int': sex_int,
                'W_total': W_total,
                'CK1': CK1,
                'CK2': CK2,
                'CM1': CM1,
                'CM2': CM2,
                'CM3': CM3,
                'CM4': CM4,
                'CM6': CM6,
                'CM7': CM7,
                'CM16': CM16,
                'CRD4': CRD4,
                'CRD5': CRD5,
                'CRD6': CRD6,
                'CRD7': CRD7,
                'Z': Z,
                'BC': BC,
                'A_foet': A_foet,
                'A_y': A_y,
                'CK5': CK5,
                'CK6': CK6,
                'CK8': CK8,
                'CP1': CP1,
                'CP4': CP4,
                'CP5': CP5,
                'CP8': CP8,
                'CP9': CP9,
                'CP10': CP10,
                'CP15': CP15,
                'CL0': CL0,
                'CL1': CL1,
                'CL2': CL2,
                'CL3': CL3,
                'CL5': CL5,
                'CL6': CL6,
                'CL15': CL15,
                'CA1': CA1,
                'CA2': CA2,
                'CA3': CA3,
                'CA4': CA4,
                'CA6': CA6,
                'CA7': CA7,
                'CW1': CW1,
                'CW2': CW2,
                'CW3': CW3,
                'CW5': CW5,
                'CW6': CW6,
                'CW7': CW7,
                'CW8': CW8,
                'CW9': CW9,
                'CW12': CW12,
            }
        }
        veg_trait_table = {
            1: {
                'digestibility_intercept': digestibility_intercept,
                'digestibility_slope': digestibility_slope,
            }
        }
        month_reg = {
            'animal_density': os.path.join(
                self.workspace_dir, 'animal_density.tif'),
            'flgrem_1': os.path.join(self.workspace_dir, 'flgrem_1.tif'),
            'fdgrem_1': os.path.join(self.workspace_dir, 'fdgrem_1.tif'),
            'diet_sufficiency': os.path.join(
                self.workspace_dir, 'diet_sufficiency.tif')
        }
        create_constant_raster(month_reg['animal_density'], stocking_density)
        create_constant_raster(month_reg['flgrem_1'], flgrem)
        create_constant_raster(month_reg['fdgrem_1'], fdgrem)

        # non-breeding goat
        diet_sufficiency = 0.4476615

        forage._animal_diet_sufficiency(
            sv_reg, pft_id_set, aligned_inputs, animal_trait_table,
            veg_trait_table, current_month, month_reg)

        self.assert_all_values_in_raster_within_range(
            month_reg['diet_sufficiency'], diet_sufficiency - tolerance,
            diet_sufficiency + tolerance, _TARGET_NODATA)

    def test_initial_conditions_from_tables(self):
        """Test `initial_conditions_from_tables`.

        Use `initial_conditions_from_tables` to generate the initial state
        variable registry from initial conditions tables.

        Raises:
            AssertionError if `initial_conditions_from_tables` does not raise
                ValueError with incomplete initial conditions tables

        Returns:
            None

        """
        from rangeland_production import forage

        # known inputs
        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['pft_1'], 1)
        sv_dir = self.workspace_dir
        pft_id_set = [1]

        site_initial_conditions_table = {
            1: {
                'metabc_1': 1.2,
                'metabc_2': 1.2,
                'som1c_1': 1.2,
                'som1c_2': 1.2,
                'som2c_1': 1.2,
                'som2c_2': 1.2,
                'som3c': 1.2,
                'strucc_1': 1.2,
                'strucc_2': 1.2,
                'strlig_1': 1.2,
                'strlig_2': 1.2,
                'metabe_1_1': 1.2,
                'metabe_2_1': 1.2,
                'som1e_1_1': 1.2,
                'som1e_2_1': 1.2,
                'som2e_1_1': 1.2,
                'som2e_2_1': 1.2,
                'som3e_1': 1.2,
                'struce_1_1': 1.2,
                'struce_2_1': 1.2,
                'metabe_1_2': 1.2,
                'metabe_2_2': 1.2,
                'plabil': 1.2,
                'secndy_2': 1.2,
                'parent_2': 1.2,
                'occlud': 1.2,
                'som1e_1_2': 1.2,
                'som1e_2_2': 1.2,
                'som2e_1_2': 1.2,
                'som2e_2_2': 1.2,
                'som3e_2': 1.2,
                'struce_1_2': 1.2,
                'struce_2_2': 1.2,
                'asmos_1': 1.2,
                'asmos_2': 1.2,
                'asmos_3': 1.2,
                'asmos_4': 1.2,
                'asmos_5': 1.2,
                'asmos_6': 1.2,
                'asmos_7': 1.2,
                'asmos_8': 1.2,
                'asmos_9': 1.2,
                'avh2o_3': 1.2,
                'minerl_1_1': 1.2,
                'minerl_2_1': 1.2,
                'minerl_3_1': 1.2,
                'minerl_4_1': 1.2,
                'minerl_5_1': 1.2,
                'minerl_6_1': 1.2,
                'minerl_7_1': 1.2,
                'minerl_8_1': 1.2,
                'minerl_9_1': 1.2,
                'minerl_10_1': 1.2,
                'minerl_1_2': 1.2,
                'minerl_2_2': 1.2,
                'minerl_3_2': 1.2,
                'minerl_4_2': 1.2,
                'minerl_5_2': 1.2,
                'minerl_6_2': 1.2,
                'minerl_7_2': 1.2,
                'minerl_8_2': 1.2,
                'minerl_9_2': 1.2,
                'minerl_10_2': 1.2,
                'snow': 1.2,
                'snlq': 1.2,
            },
        }
        pft_initial_conditions_table = {
            1: {
                'aglivc': 1.2,
                'bglivc': 1.2,
                'stdedc': 1.2,
                'aglive_1': 1.2,
                'bglive_1': 1.2,
                'stdede_1': 1.2,
                'aglive_2': 1.2,
                'bglive_2': 1.2,
                'stdede_2': 1.2,
                'avh2o_1': 1.2,
                'crpstg_1': 1.2,
                'crpstg_2': 1.2,
            },
        }

        # complete inputs
        initial_sv_reg = forage.initial_conditions_from_tables(
            aligned_inputs, sv_dir, pft_id_set, site_initial_conditions_table,
            pft_initial_conditions_table)

        # site state variable missing from initial conditions table
        site_initial_conditions_table = {
            1: {
                'metabc_1': 1.2,
                'metabc_2': 1.2,
                'som1c_1': 1.2,
                'som1c_2': 1.2,
                'som2c_1': 1.2,
                'som2c_2': 1.2,
                'som3c': 1.2,
                'strucc_1': 1.2,
                'strucc_2': 1.2,
                'strlig_1': 1.2,
                'strlig_2': 1.2,
                'metabe_1_1': 1.2,
                'metabe_2_1': 1.2,
                'som1e_1_1': 1.2,
                'som1e_2_1': 1.2,
                'som2e_1_1': 1.2,
                'som2e_2_1': 1.2,
                'som3e_1': 1.2,
                'struce_1_1': 1.2,
                'struce_2_1': 1.2,
                'metabe_1_2': 1.2,
                'metabe_2_2': 1.2,
                'plabil': 1.2,
                'secndy_2': 1.2,
                'parent_2': 1.2,
                'occlud': 1.2,
                'som1e_1_2': 1.2,
                'som1e_2_2': 1.2,
                'som2e_1_2': 1.2,
                'som2e_2_2': 1.2,
                'som3e_2': 1.2,
                'struce_1_2': 1.2,
                'struce_2_2': 1.2,
                'asmos_2': 1.2,
                'asmos_3': 1.2,
                'asmos_4': 1.2,
                'asmos_5': 1.2,
                'asmos_6': 1.2,
                'asmos_7': 1.2,
                'asmos_8': 1.2,
                'asmos_9': 1.2,
                'avh2o_3': 1.2,
                'minerl_2_1': 1.2,
                'minerl_3_1': 1.2,
                'minerl_4_1': 1.2,
                'minerl_5_1': 1.2,
                'minerl_6_1': 1.2,
                'minerl_7_1': 1.2,
                'minerl_8_1': 1.2,
                'minerl_9_1': 1.2,
                'minerl_10_1': 1.2,
                'minerl_1_2': 1.2,
                'minerl_2_2': 1.2,
                'minerl_3_2': 1.2,
                'minerl_4_2': 1.2,
                'minerl_5_2': 1.2,
                'minerl_6_2': 1.2,
                'minerl_7_2': 1.2,
                'minerl_8_2': 1.2,
                'minerl_9_2': 1.2,
                'minerl_10_2': 1.2,
                'snlq': 1.2,
            },
        }

        # asmos_1, minerl_1_1, snow missing
        with self.assertRaises(ValueError):
            initial_sv_reg = forage.initial_conditions_from_tables(
                aligned_inputs, sv_dir, pft_id_set,
                site_initial_conditions_table, pft_initial_conditions_table)

        # pft state variable missing from initial conditions table
        site_initial_conditions_table = {
            1: {
                'metabc_1': 1.2,
                'metabc_2': 1.2,
                'som1c_1': 1.2,
                'som1c_2': 1.2,
                'som2c_1': 1.2,
                'som2c_2': 1.2,
                'som3c': 1.2,
                'strucc_1': 1.2,
                'strucc_2': 1.2,
                'strlig_1': 1.2,
                'strlig_2': 1.2,
                'metabe_1_1': 1.2,
                'metabe_2_1': 1.2,
                'som1e_1_1': 1.2,
                'som1e_2_1': 1.2,
                'som2e_1_1': 1.2,
                'som2e_2_1': 1.2,
                'som3e_1': 1.2,
                'struce_1_1': 1.2,
                'struce_2_1': 1.2,
                'metabe_1_2': 1.2,
                'metabe_2_2': 1.2,
                'plabil': 1.2,
                'secndy_2': 1.2,
                'parent_2': 1.2,
                'occlud': 1.2,
                'som1e_1_2': 1.2,
                'som1e_2_2': 1.2,
                'som2e_1_2': 1.2,
                'som2e_2_2': 1.2,
                'som3e_2': 1.2,
                'struce_1_2': 1.2,
                'struce_2_2': 1.2,
                'asmos_1': 1.2,
                'asmos_2': 1.2,
                'asmos_3': 1.2,
                'asmos_4': 1.2,
                'asmos_5': 1.2,
                'asmos_6': 1.2,
                'asmos_7': 1.2,
                'asmos_8': 1.2,
                'asmos_9': 1.2,
                'avh2o_3': 1.2,
                'minerl_1_1': 1.2,
                'minerl_2_1': 1.2,
                'minerl_3_1': 1.2,
                'minerl_4_1': 1.2,
                'minerl_5_1': 1.2,
                'minerl_6_1': 1.2,
                'minerl_7_1': 1.2,
                'minerl_8_1': 1.2,
                'minerl_9_1': 1.2,
                'minerl_10_1': 1.2,
                'minerl_1_2': 1.2,
                'minerl_2_2': 1.2,
                'minerl_3_2': 1.2,
                'minerl_4_2': 1.2,
                'minerl_5_2': 1.2,
                'minerl_6_2': 1.2,
                'minerl_7_2': 1.2,
                'minerl_8_2': 1.2,
                'minerl_9_2': 1.2,
                'minerl_10_2': 1.2,
                'snow': 1.2,
                'snlq': 1.2,
            },
        }
        pft_initial_conditions_table = {
            1: {
                'aglivc': 1.2,
                'bglivc': 1.2,
                'stdedc': 1.2,
                'aglive_1': 1.2,
                'stdede_1': 1.2,
                'aglive_2': 1.2,
                'bglive_2': 1.2,
                'stdede_2': 1.2,
                'crpstg_1': 1.2,
                'crpstg_2': 1.2,
            },
        }

        # should list bglive_1 and avh2o_1 as missing
        with self.assertRaises(ValueError):
            initial_sv_reg = forage.initial_conditions_from_tables(
                aligned_inputs, sv_dir, pft_id_set,
                site_initial_conditions_table, pft_initial_conditions_table)

    def test_check_pft_fractional_cover_sum(self):
        """Test `_check_pft_fractional_cover_sum`.

        Use `_check_pft_fractional_cover_sum` to check the sum of fractional
        cover across plant functional types. Ensure that
        `_check_pft_fractional_cover_sum` raises a ValueError when the sum of
        fractional cover across plant functional types exceeds 1.

        Raises:
            AssertionError if `_check_pft_fractional_cover_sum` does not raise
                ValueError with invalid inputs

        Returns:
            None

        """
        from rangeland_production import forage

        # valid inputs, single plant functional type
        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['pft_1'], 1)
        pft_id_set = [1]

        forage._check_pft_fractional_cover_sum(aligned_inputs, pft_id_set)

        # valid inputs, multiple plant functional types
        aligned_inputs = {
            'site_index': os.path.join(self.workspace_dir, 'site.tif'),
            'pft_1': os.path.join(self.workspace_dir, 'pft_1.tif'),
            'pft_4': os.path.join(self.workspace_dir, 'pft_4.tif'),
            'pft_5': os.path.join(self.workspace_dir, 'pft_5.tif'),
        }
        create_constant_raster(aligned_inputs['site_index'], 1)
        create_constant_raster(aligned_inputs['pft_1'], 0.3)
        create_constant_raster(aligned_inputs['pft_4'], 0.2)
        create_constant_raster(aligned_inputs['pft_5'], 0.497)
        pft_id_set = [1, 4, 5]

        forage._check_pft_fractional_cover_sum(aligned_inputs, pft_id_set)

        # invalid inputs, sum of fractional cover exceeds 1
        create_constant_raster(aligned_inputs['pft_4'], 0.3)
        with self.assertRaises(ValueError):
            forage._check_pft_fractional_cover_sum(aligned_inputs, pft_id_set)
