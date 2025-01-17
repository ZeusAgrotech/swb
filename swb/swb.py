import numpy as np
import pandas as pd

def calculate_soil_water(**kwargs):
    model = SoilWaterBalance(**kwargs)
    model.calculate_timeseries()
    return {"raw": model.raw, "taw": model.taw, "timeseries": kwargs["timeseries"]}


class SoilWaterBalance(object):
    # Symbols we use:
    # theta_s - Water content at saturation
    # theta_fc - Water content at field capacity
    # theta_wp - Water content at wilting point
    # theta_init - Initial water content
    # zr - Root zone depth
    # zr_factor - Unit change factor for reducing zr to the same unit as the time series
    # kc - Crop coefficient
    # p - Soil water depletion fraction for no stress
    # draintime - Days the soil needs to go from theta_s to theta_fc
    # raw - Readily available water
    # taw - Total available water
    # effective_precipitation - Effective precipitation
    # evapotranspiration - Reference evapotranspiration
    # crop_evapotranspiration - The reference evaporation multiplied by kc
    # actual_net_irrigation - The actual supplied net irrigation
    # recommended_net_irrigation - The calculated required net irrigation
    # ro - Surface runoff
    # cr - Capillary rise
    # dp - Deep percolation
    # dr - Root zone depletion
    # mif - Malamos irrigation factor

    def __init__(self, **kwargs):
        self.theta_s = kwargs["theta_s"]
        self.theta_fc = kwargs["theta_fc"]
        self.theta_wp = kwargs["theta_wp"]
        self.zr = kwargs["zr"]
        self.zr_factor = kwargs["zr_factor"]
        self.p = kwargs["p"]
        self.draintime = kwargs["draintime"]
        self.timeseries = kwargs["timeseries"]
        self.theta_init = kwargs["theta_init"]
        self.mif = kwargs["mif"]
        self.taw = (self.theta_fc - self.theta_wp) * self.zr * self.zr_factor
        self.raw = self.p * self.taw

    def calculate_timeseries(self):
        # Add columns to self.timeseries
        self.timeseries["dr"] = np.nan
        self.timeseries["theta"] = np.nan
        self.timeseries["ks"] = np.nan
        self.timeseries["recommended_net_irrigation"] = np.nan

        # Loop and perform the calculation
        theta_prev = self.theta_init
        for nt, date in enumerate(self.timeseries.index):

            if nt == 0:
                dr_prev = self.dr_from_theta(theta_prev,date)

            row = self.timeseries.loc[date]
            ks = self.ks(dr_prev,date)

            dr_without_irrig = self.dr_without_irrig(dr_prev, theta_prev, ks, row, date)

            ani = row["actual_net_irrigation"]
            auto_apply_irrigation = type(ani) == np.bool_ and ani
            assumed_net_irrigation = 0 if auto_apply_irrigation else ani
            dr = dr_without_irrig - assumed_net_irrigation
            recommended_net_irrigation = dr * self.mif if dr > self.raw.loc[date].values[0] else 0
            if auto_apply_irrigation and dr_without_irrig > self.raw.loc[date].values[0]:
                dr = dr_without_irrig - recommended_net_irrigation

            theta = self.theta_from_dr(dr,date)
            self.timeseries.at[date, "dr"] = dr
            self.timeseries.at[date, "theta"] = theta
            self.timeseries.at[date, "ks"] = ks
            self.timeseries.at[
                date, "recommended_net_irrigation"
            ] = recommended_net_irrigation
            theta_prev = theta
            dr_prev = dr

    def dr_from_theta(self, theta, date):
        return (self.theta_fc - theta) * self.zr.loc[date][0] * self.zr_factor

    def theta_from_dr(self, dr, date):
        return self.theta_fc - dr / (self.zr.loc[date][0] * self.zr_factor)

    def ks(self, dr,date):
        result=((self.taw.loc[date].values[0] - dr) /
                ((1 - self.p.loc[date].values[0]) *
                 self.taw.loc[date].values[0]))
        return min(result, 1)

    def ro(self, effective_precipitation, theta_prev, date):
        result = (
            effective_precipitation
            + (theta_prev - self.theta_s) * self.zr.loc[date].values[0]
            * self.zr_factor
        )
        return max(result,0)

    def dp(self, theta_prev, peff, date):
        theta = min(theta_prev, self.theta_s)
        theta_mm = theta * self.zr.loc[date].values[0] * self.zr_factor
        theta_fc_mm = self.theta_fc * self.zr.loc[date].values[0] * self.zr_factor
        excess_water = theta_mm - theta_fc_mm + peff
        return max(excess_water, 0) / self.draintime

    def dr_without_irrig(self, dr_prev, theta_prev, ks, row,date):
        # "row" is a single row from self.timeseries

        result = (
            dr_prev
            - (
                row["effective_precipitation"]
                - self.ro(row["effective_precipitation"], theta_prev, date)
            )
            + row["crop_evapotranspiration"] * ks
            + self.dp(theta_prev, row["effective_precipitation"], date)
        )
        return min(result, self.taw.loc[date].values[0])

