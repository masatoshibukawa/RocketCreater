"""Utilities for simulating a water rocket flight.

The module exposes the :class:`WaterRocket` model and helper routines that
compute expulsion flow, thrust, and trajectory over time.
"""

#Import libaries
import numpy as np
from matplotlib import cm
from matplotlib.patches import Patch
import pygame
import sys
import matplotlib.pyplot as plt
import pandas as pd
from constants import *
from utilities import *

#Fly 8bar s1 0.850 s2 1.15
# s1 water, s1 air, s2 water, s2 air
# 0.12s, 0.265s, 0.945s, 2.26s 

class WaterRocket():
    """Model a water rocket and provide several function to simulate its flight.
    """

    def __init__(self,
                 s1_nozzleDiameter = 0.020,
                 s2_nozzleDiameter = 0.007,
                 s1_bottleCount = 1,
                 s2_bottleCount = 2,
                 bottleType = CST_BOTTLE_TYPE_2L,
                 rocket_payloadMass = 0.2):
        """Initialize the water rocket model.

        Args:
            s1_nozzleDiameter (float): Nozzle diameter in meter of the lower reservoir
                of the rocket.
                The default diameter is 20mm which is the diameter of a 2L soda bottle.
            s2_nozzleDiameter (float): Nozzle diameter in meter of the upper reservoir
                of the rocket.
                The default diameter is 7mm which correspond the the internal diameter
                the water ejection tube use in the current rocket design.
            s1_bottleCount (int): Number of bottles in lower reservoir. Default is 1.
            s2_bottleCount (int): Number of bottles in upper reservoir. Default is 2.
            bottleType (str): Constant that identifies the bottle type.
                Default is 2L bootle.
            rocket_payloadMass (float): Payload mass in kilograms. Default is 0.2kg
                which is a raisonable payload mass for a water rocket.
        """
        self.s1_nozzleDiameter = s1_nozzleDiameter
        self.s2_nozzleDiameter = s2_nozzleDiameter
        self.s1_bottleCount = s1_bottleCount
        self.s2_bottleCount = s2_bottleCount
        self.rocket_payloadMass = rocket_payloadMass

        self.bottleType = bottleType
        if self.bottleType == CST_BOTTLE_TYPE_2L:
            self.bottleMass = CST_BOTTLE_2L_MASS
            self.bottleVolume = CST_BOTTLE_2L_VOLUME
            self.bottleDiameter = CST_BOTTLE_2L_DIAMETER
        elif self.bottleType == CST_BOTTLE_TYPE_1dot5L:
            self.bottleMass = CST_BOTTLE_1dot5L_MASS
            self.bottleVolume = CST_BOTTLE_1dot5L_VOLUME
            self.bottleDiameter = CST_BOTTLE_1dot5L_DIAMETER

    def _waterExpulsionVelocity(self,
                                pressure,
                                nozzleDiameter,
                                rocketDiameter):
        """Compute the expulsion velocity of water from the rocket nozzle. Based on
        Bernoulli's equation or Torricelli's law.

        Args:
            pressure (float): Pressure inside the rocket in Pascals.
            nozzleDiameter (float): Diameter of the rocket nozzle in meters.
            rocketDiameter (float): Diameter of the rocket in meters.
        
        Returns:
            float: Expulsion velocity in meters per second.
        """
        nozzleArea = circleArea(nozzleDiameter)
        rocketArea = circleArea(rocketDiameter)

        if (pressure > CST_ATMOSPHERIC_PRESSURE):
            expulsionVelocity= np.sqrt(2 * (1/(1-(nozzleArea/rocketArea)**2))*((pressure-CST_ATMOSPHERIC_PRESSURE)/CST_WATER_DENSITY)) 
        else:
            expulsionVelocity = 0

        return expulsionVelocity

    def _airExpulsionMassFlowShocked(self,
                                     pressure,
                                     nozzleDiameter,
                                     restriction):
        """Compute the mass flow of air expulsion from the rocket nozzle in case of
        choked flow. Based on the choked flow law.

        Args:
            pressure (float): Pressure inside the rocket in Pascals.
            nozzleDiameter (float): Diameter of the rocket nozzle in meters.
            restriction (float): Flow restriction coefficient (between 0 and 1).
        Returns:
            float: Mass flow of air expulsion in kg/s.
        """
        massFlow = 0
        nozzleArea = circleArea(nozzleDiameter)
        massFlow = restriction * nozzleArea * pressure * np.sqrt((CST_HEAT_CAPACITY_RATIO * CST_MASS_MOLAIRE_AIR) / (CST_PERFECT_GAS_CONSTANT * CST_AMBIANT_TEMPERATURE)) * ((2 / (CST_HEAT_CAPACITY_RATIO + 1)) ** ((CST_HEAT_CAPACITY_RATIO + 1) / (2 * (CST_HEAT_CAPACITY_RATIO - 1))))
        return massFlow

    def _airExpulsionMassFlowIsentropic(self,
                                        pressure,
                                        nozzleDiameter,
                                        restriction):
        """Compute the mass flow of air expulsion from the rocket nozzle in case of
        isentropic flow. Based on the isentropic flow law.
        
        Args:
            pressure (float): Pressure inside the rocket in Pascals.
            nozzleDiameter (float): Diameter of the rocket nozzle in meters.
            restriction (float): Flow restriction coefficient (between 0 and 1).
        Returns:
            float: Mass flow of air expulsion in kg/s.
        """
        massFlow = 0
        nozzleArea = circleArea(nozzleDiameter)
        massFlow = restriction * nozzleArea * pressure * np.sqrt( ( 2 * CST_HEAT_CAPACITY_RATIO / ( ( CST_PERFECT_GAS_CONSTANT / CST_MASS_MOLAIRE_AIR ) * CST_AMBIANT_TEMPERATURE * ( CST_HEAT_CAPACITY_RATIO - 1 ) ) ) * ( ( ( CST_ATMOSPHERIC_PRESSURE / pressure ) ** ( 2 / CST_HEAT_CAPACITY_RATIO ) ) * ( 1 - (CST_ATMOSPHERIC_PRESSURE / pressure ) ** ( ( CST_HEAT_CAPACITY_RATIO - 1 ) / CST_HEAT_CAPACITY_RATIO ) ) ) ) 
        return massFlow

    def _airExpulsionVelocityIsentropic(self,
                                        pressure):
        """Compute the expulsion velocity of air from the rocket nozzle in case of
        isentropic flow.

        Args:
            pressure (float): Pressure inside the rocket in Pascals.

        Returns:
            float: Expulsion velocity of air in meters per second.
        """
        velocity = 0
        velocity = np.sqrt(((2 * CST_HEAT_CAPACITY_RATIO * (CST_PERFECT_GAS_CONSTANT / CST_MASS_MOLAIRE_AIR) * CST_AMBIANT_TEMPERATURE )/(CST_HEAT_CAPACITY_RATIO - 1))*(1 - ( CST_ATMOSPHERIC_PRESSURE / pressure )**((CST_HEAT_CAPACITY_RATIO -1)/CST_HEAT_CAPACITY_RATIO)))
        return velocity

    def _rocketEmptyMass(self):
        """Compute the empty mass of the rocket based on the number of bottles used and the payload mass.

        Returns:
            float: Empty mass of the rocket in kg.
        """
        emptyMass = self.rocket_payloadMass + (self.s1_bottleCount + self.s2_bottleCount) * self.bottleMass + CST_ROCKET_NOSE_CONE_MASS + CST_ROCKET_FIN_WEIGHT
        return emptyMass

    def _simulationStep(self,
                        flyVariables):
        """Calculate the simulation step used in the simulation.

        Args:
            flyVariables (dict): Dictionary containing the simulation results.

        Returns:
            float: Simulation step used in the simulation.
        """
        return flyVariables["time"][1] - flyVariables["time"][0]

    def _simulationTime(self,flyVariables):
        """Calculate the total simulation time.

        Args:
            flyVariables (dict): Dictionary containing the simulation results.

        Returns:
            float: Total simulation time implemented in the simulation.
        """
        return flyVariables["time"][-1]

    def launchSimulation(self,
                         simulation_step = 0.01,
                         simulation_time = 5,
                         s1_waterVolumeIni = 0.001,
                         s2_waterVolumeIni = 0.0015,
                         ):
        """Simulate the launch of the water rocket using an Euler method to evaluate the
        evolution of the rocket state (volume, mass, pressure, altitude) based on the
        evolution of the expulsion flows and cinematic variables (speed, acceleration)
        with the help of physics laws.

        Args:
            simulation_step (float): Time step for the Euler simulation in seconds.
            simulation_time (float): Total time for the simulation in seconds.
            s1_waterVolumeIni (float, optional): Initial water volume in section 1 in
            cubic meters. Defaults to 0.001.
            s2_waterVolumeIni (float, optional): Initial water volume in section 2 in
            cubic meters. Defaults to 0.0015.
        
        Returns:
            dict: A dictionary containing the evolution of the rocket state and
            cinematic variables over time.
        """

        #calculated properties
        s1_nozzleSectionArea = circleArea(self.s1_nozzleDiameter)
        s2_nozzleSectionArea = circleArea(self.s2_nozzleDiameter)
        rocket_sectionArea = circleArea(self.bottleDiameter)

        #Rocket state
        noseConeEjected =False

        rocket_emptyMass = self._rocketEmptyMass()

        s1_volume = self.bottleVolume * self.s1_bottleCount
        s2_volume = self.bottleVolume * self.s2_bottleCount

        #Euler variables
        simulation_time = np.round(simulation_time/simulation_step)*simulation_step

        #################
        #DATA CONTAINERS
        #################

        t = np.arange(0, simulation_time + simulation_step, simulation_step)
        numberOfSteps = len(t)

        s1_pressure = np.zeros(numberOfSteps)
        s2_pressure = np.zeros(numberOfSteps)

        s1_waterExpulsionVelocity = np.zeros(numberOfSteps)
        s2_waterExpulsionVelocity = np.zeros(numberOfSteps)

        s1_waterExpulsionFlow = np.zeros(numberOfSteps)
        s2_waterExpulsionFlow = np.zeros(numberOfSteps)

        s1_waterExpulsionMassFlow = np.zeros(numberOfSteps)
        s2_waterExpulsionMassFlow = np.zeros(numberOfSteps)

        s1_waterVolume = np.zeros(numberOfSteps)
        s2_waterVolume = np.zeros(numberOfSteps)

        s1_airVolume = np.zeros(numberOfSteps)
        s2_airVolume = np.zeros(numberOfSteps)

        s1_waterMass = np.zeros(numberOfSteps)
        s2_waterMass = np.zeros(numberOfSteps)

        s1_airExpulsionVelocity = np.zeros(numberOfSteps)
        s2_airExpulsionVelocity = np.zeros(numberOfSteps)

        s1_airExpulsionFlow = np.zeros(numberOfSteps)
        s2_airExpulsionFlow = np.zeros(numberOfSteps)

        s1_airExpulsionMassFlow = np.zeros(numberOfSteps)
        s2_airExpulsionMassFlow = np.zeros(numberOfSteps)

        s1_airMass = np.zeros(numberOfSteps)
        s2_airMass = np.zeros(numberOfSteps)

        rocket_mass = np.zeros(numberOfSteps)

        rocket_weight = np.zeros(numberOfSteps)

        s1_airDensity = np.zeros(numberOfSteps)
        s2_airDensity = np.zeros(numberOfSteps)

        s1_thrustMode = np.zeros(numberOfSteps)
        s2_thrustMode = np.zeros(numberOfSteps)

        rocket_noseConeRelease = np.zeros(numberOfSteps)

        s1_thrustAir = np.zeros(numberOfSteps)
        s2_thrustAir = np.zeros(numberOfSteps)

        s1_thrustWater = np.zeros(numberOfSteps)
        s2_thrustWater = np.zeros(numberOfSteps)

        s1_thrust = np.zeros(numberOfSteps)
        s2_thrust = np.zeros(numberOfSteps)

        total_thrust = np.zeros(numberOfSteps)

        rocket_acceleration = np.zeros(numberOfSteps)
        rocket_velocity = np.zeros(numberOfSteps)
        rocket_altitude = np.zeros(numberOfSteps)

        rocket_drag = np.zeros(numberOfSteps)

        total_downforce = np.zeros(numberOfSteps)

        ################
        #INTITIALIZATION
        ################

        #Static state variable
        #----------------------

        #VOLUME

        s1_waterVolume[0] = s1_waterVolumeIni
        s2_waterVolume[0] = s2_waterVolumeIni

        s1_airVolume[0] = s1_volume - s1_waterVolume[0]
        s2_airVolume[0] = s2_volume - s2_waterVolume[0]

        #PRESSURE

        s1_pressure[0] = CST_LAUNCH_PRESSURE
        s2_pressure[0] = CST_LAUNCH_PRESSURE
        
        #MASS

        s1_waterMass[0] = s1_waterVolume[0] * CST_WATER_DENSITY
        s2_waterMass[0] = s2_waterVolume[0] * CST_WATER_DENSITY

        s1_airMass[0] = (CST_AIR_ATMOSPHERIC_DENSITY * s1_pressure [0] * s1_airVolume[0]) / CST_ATMOSPHERIC_PRESSURE
        s2_airMass[0] = (CST_AIR_ATMOSPHERIC_DENSITY * s2_pressure [0] * s2_airVolume[0]) / CST_ATMOSPHERIC_PRESSURE

        #DENSITY

        s1_airDensity[0] = s1_airMass[0] / s1_airVolume[0]
        s2_airDensity[0] = s2_airMass[0] / s2_airVolume[0]

        #FLYING PHASE

        if s1_waterMass[0] > 0:
            s1_thrustMode[0] = CST_THRUST_MODE_WATER
        elif s1_airMass[0] > (s1_volume * CST_AIR_ATMOSPHERIC_DENSITY):
            s1_thrustMode[0] = CST_THRUST_MODE_AIR_SHOCKED
        else:
            s1_thrustMode[0] = CST_THRUST_MODE_OFF

        if s1_thrustMode[0] == CST_THRUST_MODE_WATER:
            s2_thrustMode[0] = CST_THRUST_MODE_OFF
        else:
            if s2_waterMass[0] > 0:
                s2_thrustMode[0] = CST_THRUST_MODE_WATER
            elif s2_airMass[0] > (s2_volume * CST_AIR_ATMOSPHERIC_DENSITY):
                s2_thrustMode[0] = CST_THRUST_MODE_AIR_SHOCKED
            else:
                s2_thrustMode[0] = CST_THRUST_MODE_OFF
        
        rocket_noseConeRelease[0] = False

        #ROCKET MASS
        rocket_mass[0] = rocket_emptyMass + s1_waterMass[0] + s2_waterMass[0] + s1_airMass[0] + s2_airMass[0]

        rocket_velocity[0] = 0
        rocket_altitude[0] = 0    
        
        #Dynamic state variable
        #----------------------

        s1_waterExpulsionVelocity[0] = self._waterExpulsionVelocity(s1_pressure[0], self.s1_nozzleDiameter, self.bottleDiameter) * (s1_thrustMode[0] == CST_THRUST_MODE_WATER)
        s2_waterExpulsionVelocity[0] = self._waterExpulsionVelocity(s2_pressure[0], self.s2_nozzleDiameter, self.bottleDiameter) * (s2_thrustMode[0] == CST_THRUST_MODE_WATER)

        s1_waterExpulsionFlow[0] = s1_waterExpulsionVelocity[0] * s1_nozzleSectionArea * CST_S1_waterFlowRestriction
        s2_waterExpulsionFlow[0] = s2_waterExpulsionVelocity[0] * s2_nozzleSectionArea * CST_S2_waterFlowRestriction

        s1_waterExpulsionMassFlow[0] = s1_waterExpulsionFlow[0] * CST_WATER_DENSITY
        s2_waterExpulsionMassFlow[0] = s2_waterExpulsionFlow[0] * CST_WATER_DENSITY

        s1_airExpulsionVelocity[0] = CST_AIR_THROAT_VELOCITY * (s1_thrustMode[0] == CST_THRUST_MODE_AIR_SHOCKED)
        s2_airExpulsionVelocity[0] = CST_AIR_THROAT_VELOCITY * (s2_thrustMode[0] == CST_THRUST_MODE_AIR_SHOCKED)

        s1_airExpulsionFlow[0] = s1_airExpulsionVelocity[0] * s1_nozzleSectionArea
        s2_airExpulsionFlow[0] = s2_airExpulsionVelocity[0] * s2_nozzleSectionArea

        s1_airExpulsionMassFlow[0] = self._airExpulsionMassFlowShocked(s1_pressure[0], self.s1_nozzleDiameter, CST_S1_airFlowRestriction) * (s1_thrustMode[0] == CST_THRUST_MODE_AIR_SHOCKED)
        s2_airExpulsionMassFlow[0] = self._airExpulsionMassFlowShocked(s2_pressure[0], self.s2_nozzleDiameter, CST_S2_airFlowRestriction) * (s2_thrustMode[0] == CST_THRUST_MODE_AIR_SHOCKED)

        #Force variables
        #---------------

        rocket_weight[0] = -1 * rocket_mass[0] * CST_GRAVITY
        rocket_drag[0] = 0.5 * CST_AIR_ATMOSPHERIC_DENSITY * CST_ROCKET_DRAG_COEFICIENT * rocket_sectionArea * rocket_velocity[0]**2
        total_downforce[0] = rocket_weight[0] + rocket_drag[0]

        s1_thrustWater[0] = s1_waterExpulsionMassFlow[0] * s1_waterExpulsionVelocity[0]
        s2_thrustWater[0] = s2_waterExpulsionMassFlow[0] * s2_waterExpulsionVelocity[0]

        s1_thrustAir[0] = s1_airExpulsionMassFlow[0] * s1_waterExpulsionVelocity[0]
        s2_thrustAir[0] = s2_airExpulsionMassFlow[0] * s2_waterExpulsionVelocity[0]
        
        s1_thrust[0] = s1_thrustAir[0] + s1_thrustWater[0]
        s2_thrust[0] = s2_thrustAir[0] + s2_thrustWater[0]

        total_thrust[0] = s1_thrust[0] + s2_thrust[0]

        #Cinematic variables
        #--------------------
        rocket_acceleration[0] = (total_thrust[0] + total_downforce[0]) / rocket_mass[0]
        

        i = 1
        while i < len(t):
            ####################################################################################################################
            # 1- Evaluate new state (volume, mass, pressure, altitude) base on previous step evolution (water expulsion velocity/flow,
            # air expulsion velocity/flow, rocket speed, rocket acceleration)
            ####################################################################################################################

            # VOLUME
            ########


            # Update water volumes based on expulsion flows of previous step
            s1_waterVolume[i] = s1_waterVolume[i-1] - s1_waterExpulsionFlow[i-1] * (t[i] - t[i-1])
            if s1_waterVolume[i] <= 0:
                s1_waterVolume[i] = 0
            s2_waterVolume[i] = s2_waterVolume[i-1] - s2_waterExpulsionFlow[i-1] * (t[i] - t[i-1])
            if s2_waterVolume[i] <= 0:
                s2_waterVolume[i] = 0
            
            #Update air volumes
            s1_airVolume[i] = s1_volume - s1_waterVolume[i]
            s2_airVolume[i] = s2_volume - s2_waterVolume[i]

            # MASS
            ######

            # Update water masses
            s1_waterMass[i] = s1_waterVolume[i] * CST_WATER_DENSITY
            s2_waterMass[i] = s2_waterVolume[i] * CST_WATER_DENSITY

            # Update air mass based on previous step air expulsion flows
            s1_airMass[i] = s1_airMass[i-1] - s1_airExpulsionMassFlow[i-1] * (t[i] - t[i-1])
            if s1_airMass[i] < CST_AIR_ATMOSPHERIC_DENSITY * s1_volume:
                s1_airMass[i] = CST_AIR_ATMOSPHERIC_DENSITY * s1_volume
            
            s2_airMass[i] = s2_airMass[i-1] - s2_airExpulsionMassFlow[i-1] * (t[i] - t[i-1])
            if s2_airMass[i] < (CST_AIR_ATMOSPHERIC_DENSITY * s2_volume):
                s2_airMass[i] = CST_AIR_ATMOSPHERIC_DENSITY * s2_volume
            
            # PRESSURE
            ##########

            #Calculate pressures
            s1_pressure[i] = (s1_airMass[i]/CST_MASS_MOLAIRE_AIR) * CST_PERFECT_GAS_CONSTANT * CST_AMBIANT_TEMPERATURE / s1_airVolume[i]
            s2_pressure[i] = (s2_airMass[i]/CST_MASS_MOLAIRE_AIR) * CST_PERFECT_GAS_CONSTANT * CST_AMBIANT_TEMPERATURE / s2_airVolume[i]
            
            #DENSITY
            s1_airDensity[i] = s1_airMass[i] / s1_airVolume[i]
            s2_airDensity[i] = s2_airMass[i] / s2_airVolume[i]
            
            #FLYING PHASE
            if s1_waterMass[i] > 0:
                s1_thrustMode[i] = CST_THRUST_MODE_WATER
            else:
                if s1_airMass[i] > (s1_volume * CST_AIR_ATMOSPHERIC_DENSITY):
                    if s1_pressure[i] > CST_SHOCK_FLOW_PRESSURE:
                        s1_thrustMode[i] = CST_THRUST_MODE_AIR_SHOCKED
                    else:
                        s1_thrustMode[i] = CST_THRUST_MODE_AIR_ISENTROPIC
                else:
                    s1_thrustMode[i] = CST_THRUST_MODE_OFF
            if (s1_thrustMode[i] != CST_THRUST_MODE_WATER) and (s2_volume > 0):
                if (s2_waterMass[i] > 0):
                    s2_thrustMode[i] = CST_THRUST_MODE_WATER
                else:
                    if s2_airMass[i] > (s2_volume * CST_AIR_ATMOSPHERIC_DENSITY):
                        if s2_pressure[i] > CST_SHOCK_FLOW_PRESSURE:
                            s2_thrustMode[i] = CST_THRUST_MODE_AIR_SHOCKED
                        else:
                            s2_thrustMode[i] = CST_THRUST_MODE_AIR_ISENTROPIC
                    else:
                        s2_thrustMode[i] = CST_THRUST_MODE_OFF
            else:
                s2_thrustMode[i] = CST_THRUST_MODE_OFF
                
            #ALTITUDE
            #########

            # Update altitude
            rocket_altitude[i] = rocket_altitude[i-1] + rocket_velocity[i-1] * (t[i] - t[i-1])

            if rocket_noseConeRelease[i-1]:
                rocket_noseConeRelease[i] = True
            elif (rocket_altitude[i-1] > rocket_altitude[i]) and not rocket_noseConeRelease[i-1]:
                rocket_noseConeRelease[i] = True
                rocket_emptyMass = rocket_emptyMass - self.rocket_payloadMass - CST_ROCKET_NOSE_CONE_MASS
            else:
                rocket_noseConeRelease[i] = False

            #ROCKET MASS
            rocket_mass[i] = rocket_emptyMass + s1_waterMass[i] + s2_waterMass[i] + s1_airMass[i] + s2_airMass[i]

            # SPEED
            ########

            # Update velocity

            rocket_velocity[i] = rocket_velocity[i-1] + rocket_acceleration[i-1] * (t[i] - t[i-1])       
                

            ####################################################################################################################
            # 2- Update evolution variables (water expulsion flow, air expulsion flow) based on new state with the help of physics laws
            ####################################################################################################################

            # Update water expulsion velocities based on Bernoulli's equation or Torricelli's law.
            s1_waterExpulsionVelocity[i] = self._waterExpulsionVelocity(s1_pressure[i], self.s1_nozzleDiameter, self.bottleDiameter) * (s1_thrustMode[i] == CST_THRUST_MODE_WATER)
            s2_waterExpulsionVelocity[i] = self._waterExpulsionVelocity(s2_pressure[i], self.s2_nozzleDiameter, self.bottleDiameter) * (s2_thrustMode[i] == CST_THRUST_MODE_WATER)

            # Update water expulsion flows
            s1_waterExpulsionFlow[i] = s1_waterExpulsionVelocity[i] * s1_nozzleSectionArea * CST_S1_waterFlowRestriction
            if s2_volume > 0:
                s2_waterExpulsionFlow[i] = s2_waterExpulsionVelocity[i] * s2_nozzleSectionArea * CST_S2_waterFlowRestriction
            else:
                s2_waterExpulsionFlow[i] = 0

            s1_waterExpulsionMassFlow[i] = s1_waterExpulsionFlow[i] * CST_WATER_DENSITY
            if s2_volume > 0:
                s2_waterExpulsionMassFlow[i] = s2_waterExpulsionFlow[i] * CST_WATER_DENSITY
            else:
                s2_waterExpulsionMassFlow[i] = 0
            
            # Update air expulsion velocities based on choked flow law
            s1_airExpulsionVelocity[i] = CST_AIR_THROAT_VELOCITY * (s1_thrustMode[i] == CST_THRUST_MODE_AIR_SHOCKED) + self._airExpulsionVelocityIsentropic(s1_pressure[i]) * (s1_thrustMode[i] == CST_THRUST_MODE_AIR_ISENTROPIC)
            if s2_volume > 0:
                s2_airExpulsionVelocity[i] = CST_AIR_THROAT_VELOCITY  * (s2_thrustMode[i] == CST_THRUST_MODE_AIR_SHOCKED) + self._airExpulsionVelocityIsentropic(s2_pressure[i]) * (s2_thrustMode[i] == CST_THRUST_MODE_AIR_ISENTROPIC)
            else:
                s2_airExpulsionVelocity[i] = 0
            s1_airExpulsionFlow[i] = s1_airExpulsionVelocity[i] * s1_nozzleSectionArea
            if s2_volume > 0:
                s2_airExpulsionFlow[i] = s2_airExpulsionVelocity[i] * s2_nozzleSectionArea
            else:
                s2_airExpulsionFlow[i] = 0
            s1_airExpulsionMassFlow[i] = self._airExpulsionMassFlowShocked(s1_pressure[i], self.s1_nozzleDiameter, CST_S1_airFlowRestriction) * (s1_thrustMode[i] == CST_THRUST_MODE_AIR_SHOCKED) + self._airExpulsionMassFlowIsentropic(s1_pressure[i], self.s1_nozzleDiameter, CST_S1_airFlowRestriction) * (s1_thrustMode[i] == CST_THRUST_MODE_AIR_ISENTROPIC)
            if s2_volume > 0:
                s2_airExpulsionMassFlow[i] = self._airExpulsionMassFlowShocked(s2_pressure[i], self.s2_nozzleDiameter, CST_S2_airFlowRestriction) * (s2_thrustMode[i] == CST_THRUST_MODE_AIR_SHOCKED) + self._airExpulsionMassFlowIsentropic(s2_pressure[i], self.s2_nozzleDiameter, CST_S2_airFlowRestriction) * (s2_thrustMode[i] == CST_THRUST_MODE_AIR_ISENTROPIC)
            else:
                s2_airExpulsionMassFlow[i] = 0
            #Force variables
            #---------------

            # Update rocket weight
            rocket_weight[i] = -1 * rocket_mass[i] * CST_GRAVITY
            # Update drag
            rocket_drag[i] = - np.sign(rocket_velocity[i]) * 0.5 * CST_AIR_ATMOSPHERIC_DENSITY * CST_ROCKET_DRAG_COEFICIENT * rocket_sectionArea * rocket_velocity[i]**2
            total_downforce[i] = rocket_weight[i] + rocket_drag[i]
            
            s1_thrustWater[i] = s1_waterExpulsionMassFlow[i] * s1_waterExpulsionVelocity[i]
            s2_thrustWater[i] = s2_waterExpulsionMassFlow[i] * s2_waterExpulsionVelocity[i]

            s1_thrustAir[i] = s1_airExpulsionMassFlow[i] * s1_waterExpulsionVelocity[i]
            s2_thrustAir[i] = s2_airExpulsionMassFlow[i] * s2_waterExpulsionVelocity[i]
            
            s1_thrust[i] = s1_thrustAir[i] + s1_thrustWater[i]
            s2_thrust[i] = s2_thrustAir[i] + s2_thrustWater[i]

            total_thrust[i] = s1_thrust[i] + s2_thrust[i]

            # Update acceleration
            rocket_acceleration[i] = (total_thrust[i] + total_downforce[i]) / rocket_mass[i]
            
            # Check if rocket has reached the ground
            if (rocket_altitude[i] <= 0) and (i > 2):
                i=len(t)

            i += 1

        # Create a dictionary to store the results
        flyVariables = {"time": t,
                        "s1_waterVolume": s1_waterVolume,
                        "s2_waterVolume": s2_waterVolume,
                        "s1_airVolume": s1_airVolume,
                        "s2_airVolume" : s2_airVolume,
                        "s1_waterMass": s1_waterMass,
                        "s2_waterMass": s2_waterMass,
                        "s1_airMass": s1_airMass,
                        "s2_airMass": s2_airMass,
                        "s1_pressure": s1_pressure,
                        "s2_pressure": s2_pressure,
                        "s1_airDensity": s1_airDensity,
                        "s2_airDensity" : s2_airDensity,
                        "s1_thrustMode" : s1_thrustMode,
                        "s2_thrustMode" : s2_thrustMode,
                        "rocket_noseConeRelease" : rocket_noseConeRelease,
                        "rocket_mass": rocket_mass,
                        "rocket_velocity": rocket_velocity,
                        "rocket_altitude": rocket_altitude,
                        "s1_waterExpulsionVelocity": s1_waterExpulsionVelocity,
                        "s2_waterExpulsionVelocity": s2_waterExpulsionVelocity,
                        "s1_waterExpulsionFlow": s1_waterExpulsionFlow,
                        "s2_waterExpulsionFlow": s2_waterExpulsionFlow,
                        "s1_waterExpulsionMassFlow" : s1_waterExpulsionMassFlow,
                        "s2_waterExpulsionMassFlow" : s2_waterExpulsionMassFlow,
                        "s1_airExpulsionVelocity": s1_airExpulsionVelocity,
                        "s2_airExpulsionVelocity": s2_airExpulsionVelocity,
                        "s1_airExpulsionFlow": s1_airExpulsionFlow,
                        "s2_airExpulsionFlow": s2_airExpulsionFlow,
                        "s1_airExpulsionMassFlow": s1_airExpulsionMassFlow,
                        "s2_airExpulsionMassFlow": s2_airExpulsionMassFlow,
                        "rocket_weight": rocket_weight,
                        "rocket_drag": rocket_drag,
                        "total_downforce": total_downforce,
                        "s1_thrustWater" : s1_thrustWater,
                        "s2_thrustWater" : s2_thrustWater,
                        "s1_thrustAir" : s1_thrustAir,
                        "s2_thrustAir" : s2_thrustAir,
                        "s1_thrust": s1_thrust,
                        "s2_thrust": s2_thrust,
                        "total_thrust": total_thrust,
                        "rocket_acceleration": rocket_acceleration}

        
        # Return the results
        return flyVariables

    def maxAltitude(self,
                    flyVariables):
        """Calculate the maximum altitude reached by the rocket.

        Args:
            flyVariables (dict): Dictionary containing the simulation results.

        Returns:
            float: Maximum altitude reached by the rocket.
        """
        return np.max(flyVariables["rocket_altitude"])

    def timeToMaxAltitude(self,
                          flyVariables):
        """Calculate the time taken to reach the maximum altitude.

        Args:
            flyVariables (dict): Dictionary containing the simulation results.

        Returns:
            float: Time taken to reach the maximum altitude.
        """
        max_altitude_index = np.argmax(flyVariables["rocket_altitude"])
        return max_altitude_index * (flyVariables["time"][1] - flyVariables["time"][0])

    def flyTime(self,
                flyVariables):
        """Calculate the total flight time until the rocket lands.

        Args:
            flyVariables (dict): Dictionary containing the simulation results.

        Returns:
            float: Total flight time until the rocket lands.
        """
        return np.sum(flyVariables["rocket_altitude"] > 0) * 0.01

    def parametersForMaxAltitude(self,
                                 s1_waterVolumeIni_range=np.arange(0.0005, 0.001, 0.0001),
                                 s2_waterVolumeIni_range=np.arange(0.0005, 0.002, 0.0001),
                                 simulation_step=0.01,
                                 simulation_time=20
                                 ):
        """Search for the initial water volumes that maximize altitude.

        Args:
            s1_waterVolumeIni_range (np.ndarray): Range of initial S1 water volumes.
            s2_waterVolumeIni_range (np.ndarray): Range of initial S2 water volumes.
            simulation_step (float): Time step for the simulation in seconds.
            simulation_time (float): Total simulation duration in seconds.

        Returns:
            dict: Best parameters for maximum altitude and the associated altitude.
        """
        maxAltitude_value = 0
        best_s1_nozzleDiameter = 0
        best_s2_nozzleDiameter = 0
        best_s1_waterVolumeIni = 0
        best_s2_waterVolumeIni = 0
        for s1_waterVolumeIni in s1_waterVolumeIni_range:
            for s2_waterVolumeIni in s2_waterVolumeIni_range:
                flyParameters = self.launchSimulation(
                    s1_waterVolumeIni=s1_waterVolumeIni,
                    s2_waterVolumeIni=s2_waterVolumeIni,
                    simulation_step=simulation_step,
                    simulation_time=simulation_time)
                altitude = self.maxAltitude(flyParameters)
                if altitude > maxAltitude_value:
                    maxAltitude_value = altitude
                    best_s1_nozzleDiameter = self.s1_nozzleDiameter
                    best_s2_nozzleDiameter = self.s2_nozzleDiameter
                    best_s1_waterVolumeIni = s1_waterVolumeIni
                    best_s2_waterVolumeIni = s2_waterVolumeIni
        
        return {
            "s1_nozzleDiameter": best_s1_nozzleDiameter,
            "s2_nozzleDiameter": best_s2_nozzleDiameter,
            "s1_waterVolumeIni": best_s1_waterVolumeIni,
            "s2_waterVolumeIni": best_s2_waterVolumeIni,
            "maxAltitude": maxAltitude_value
        }

    def parametersForMaxTime(self,
                             payload_mass,
                             s2_bottleCount=2,
                             s2_nozzleDiameter_range=np.arange(0.005, 0.011, 0.001),
                             s1_waterVolumeIni_range=np.arange(0.0005, 0.001, 0.0001),
                             s2_waterVolumeIni_range=np.arange(0.0005, 0.002, 0.0001),
                             ):
        """Search for the parameters that maximize flight time.

        Args:
            payload_mass (float): Mass of the payload in kg.
            s2_bottleCount (int): Number of S2 bottles.
            s2_nozzleDiameter_range (np.ndarray): Range of S2 nozzle diameters.
            s1_waterVolumeIni_range (np.ndarray): Range of initial S1 water volumes.
            s2_waterVolumeIni_range (np.ndarray): Range of initial S2 water volumes.

        Returns:
            dict: Best parameters for maximum flight time.
        """
        maxTime_value = 0
        best_s2_nozzleDiameter = 0
        best_s1_waterVolumeIni = 0
        best_s2_waterVolumeIni = 0
        for s2_nozzleDiameter in s2_nozzleDiameter_range:
            for s1_waterVolumeIni in s1_waterVolumeIni_range:
                for s2_waterVolumeIni in s2_waterVolumeIni_range:
                    flyParameters = eulerSimulation(
                        s1_waterVolumeIni=s1_waterVolumeIni,
                        s2_waterVolumeIni=s2_waterVolumeIni,
                        s2_nozzleDiameter=s2_nozzleDiameter,
                        s2_bottleCount=s2_bottleCount,
                        rocket_payloadMass=payload_mass,
                        simulation_step=0.01,
                        simulation_time=10
                    )
                    time = self.flyTime(flyParameters)
                    if time > maxTime_value:
                        maxTime_value = time
                        best_s2_nozzleDiameter = s2_nozzleDiameter
                        best_s1_waterVolumeIni = s1_waterVolumeIni
                        best_s2_waterVolumeIni = s2_waterVolumeIni
        
        return {
            "s2_nozzleDiameter": best_s2_nozzleDiameter,
            "s1_waterVolumeIni": best_s1_waterVolumeIni,
            "s2_waterVolumeIni": best_s2_waterVolumeIni
        }

    def plot_max_altitude_3d_with_s2_nozzle(self,
                                            s1_volume,
                                            s2_volume,
                                            s1_nozzleDiameter,
                                            s2_nozzleDiameter_range,  # tuple: (min, max)
                                            s2_nozzleDiameter_steps,  # int: number of increments
                                            rocket_emptyMass,
                                            rocket_payloadMass,
                                            rocket_dragCoeficient,
                                            rocket_diameter,
                                            launch_Pressure
                                            ):
        """Plot maximum altitude as a 3D surface for S1/S2 water volumes and S2 nozzle diameter.

        Args:
            s1_volume (float): Total volume available in section 1 in cubic meters.
            s2_volume (float): Total volume available in section 2 in cubic meters.
            s1_nozzleDiameter (float): Nozzle diameter for section 1 in meters.
            s2_nozzleDiameter_range (tuple): Minimum and maximum S2 nozzle diameters.
            s2_nozzleDiameter_steps (int): Number of nozzle diameter increments to evaluate.
            rocket_emptyMass (float): Empty mass of the rocket in kilograms.
            rocket_payloadMass (float): Payload mass in kilograms.
            rocket_dragCoeficient (float): Drag coefficient of the rocket.
            rocket_diameter (float): Diameter of the rocket in meters.
            launch_Pressure (float): Launch pressure in Pascals.
        """

        s1_volumes = np.linspace(0, s1_volume, 20)
        s2_volumes = np.linspace(0, s2_volume, 20)
        s2_nozzleDiameters = np.linspace(s2_nozzleDiameter_range[0], s2_nozzleDiameter_range[1], s2_nozzleDiameter_steps)

        S1, S2 = np.meshgrid(s1_volumes, s2_volumes)
        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection='3d')

        # Use a colormap for different nozzle diameters
        colors = cm.viridis(np.linspace(0, 1, s2_nozzleDiameter_steps))

        for idx, (s2_nozzleDiameter, color) in enumerate(zip(s2_nozzleDiameters, colors)):
            max_altitude = np.zeros_like(S1)
            for i in range(S1.shape[0]):
                for j in range(S1.shape[1]):
                    result = eulerSimulation(
                        launch_Pressure,
                        s1_volume, S1[i, j], s1_nozzleDiameter,
                        s2_volume, S2[i, j], s2_nozzleDiameter,
                        rocket_emptyMass, rocket_payloadMass, rocket_dragCoeficient, rocket_diameter
                    )
                    max_altitude[i, j] = np.max(result["rocket_altitude"])
            # Plot as dots instead of surface
            ax.scatter(S1, S2, max_altitude, color=color, label=f'{s2_nozzleDiameter:.3f} m', alpha=0.7, s=10)

        # Create custom legend
        legend_patches = [Patch(color=colors[i], label=f'S2 Nozzle: {s2_nozzleDiameters[i]:.3f} m') for i in range(s2_nozzleDiameter_steps)]
        ax.legend(handles=legend_patches, loc='upper left', bbox_to_anchor=(1.05, 1))

        ax.set_xlabel('S1 Water Volume (m³)')
        ax.set_ylabel('S2 Water Volume (m³)')
        ax.set_zlabel('Max Altitude (m)')
        ax.set_title('Max Altitude vs S1/S2 Water Volumes for Different S2 Nozzle Diameters')
        plt.tight_layout()
        plt.show()

    def plot_flight_diagnostics(self,
                                flyParameters):
        """Plot flight diagnostics including altitude, thrust, speed, acceleration, and mass history.

        Args:
            flyParameters (dict): Simulation results dictionary returned by :meth:`launchSimulation`.
        """
        time = flyParameters["time"]
        inAirTime = self.flyTime(flyParameters)
        maxAltTime = self.timeToMaxAltitude(flyParameters)
        fig, axs = plt.subplots(3, 3, figsize=(14, 10))

        # Altitude vs Time
        axs[0, 0].plot(time, flyParameters["rocket_altitude"], label="Altitude", color="blue")
        axs[0, 0].set_title("Altitude vs Time")
        axs[0, 0].set_xlabel("Time (s)")
        axs[0, 0].set_ylabel("Altitude (m)")
        axs[0, 0].grid()
        axs[0, 0].set_xlim(0,inAirTime)
        axs[0, 0].legend()

        # Thrusts and Downforce vs Time
        axs[0, 1].plot(time, flyParameters["s1_thrust"], label="S1 Thrust", color="green")
        axs[0, 1].plot(time, flyParameters["s2_thrust"], label="S2 Thrust", color="orange")
        axs[0, 1].plot(time, flyParameters["total_thrust"], label="Total Thrust", color="red")
        axs[0, 1].plot(time, -flyParameters["total_downforce"], label="Total Downforce", color="purple", linestyle="--")
        axs[0, 1].set_title("Thrusts and Downforce vs Time")
        axs[0, 1].set_xlabel("Time (s)")
        axs[0, 1].set_ylabel("Force (N)")
        axs[0, 1].grid()
        axs[0, 1].set_xlim(0,maxAltTime)
        axs[0, 1].legend()

        # Speed vs Time
        axs[1, 0].plot(time, flyParameters["rocket_velocity"], label="Speed", color="brown")
        axs[1, 0].set_title("Speed vs Time")
        axs[1, 0].set_xlabel("Time (s)")
        axs[1, 0].set_ylabel("Speed (m/s)")
        axs[1, 0].grid()
        axs[1, 0].set_xlim(0,inAirTime)
        axs[1, 0].legend()

        # Acceleration vs Time
        axs[2, 0].plot(time, flyParameters["rocket_acceleration"], label="Acceleration", color="magenta")
        axs[2, 0].set_title("Acceleration vs Time")
        axs[2, 0].set_xlabel("Time (s)")
        axs[2, 0].set_ylabel("Acceleration (m/s²)")
        axs[2, 0].grid()
        axs[2, 0].set_xlim(0,inAirTime)
        axs[2, 0].legend()

        rocketMassVariation = flyParameters["rocket_mass"] - np.concatenate( (np.array([flyParameters["rocket_mass"][0]]),flyParameters["rocket_mass"][:-1]))
        # Cumulative sum of mass variation
        rocketCumulMassVariation = -1 * np.cumsum(rocketMassVariation)

        # Mass vs Time
        axs[1, 1].plot(time, flyParameters["rocket_mass"], label="Mass")
        axs[1, 1].plot(time, rocketCumulMassVariation, label="Cumulative Mass Variation")
        axs[1, 1].plot(time, flyParameters["s1_waterMass"], label="S1 water mass")
        axs[1, 1].plot(time, flyParameters["s2_waterMass"], label="S2 water mass")
        axs[1, 1].plot(time, flyParameters["s1_airMass"], label="S1 air mass")
        axs[1, 1].plot(time, flyParameters["s2_airMass"], label="S2 air mass")

        axs[1, 1].set_title("Mass vs Time")
        axs[1, 1].set_xlabel("Time (s)")
        axs[1, 1].set_ylabel("Mass (Kg)")
        axs[1, 1].grid()
        axs[1, 1].set_xlim(0,maxAltTime)
        axs[1, 1].legend()

        # Pressure vs Time
        axs[0, 2].plot(time, flyParameters["s1_pressure"], label="s1 pressure")
        axs[0, 2].plot(time, flyParameters["s2_pressure"], label="s2 pressure")
        axs[0, 2].set_title("Pressure vs Time")
        axs[0, 2].set_xlabel("Time (s)")
        axs[0, 2].set_ylabel("Pressure")
        axs[0, 2].grid()
        axs[0, 2].set_xlim(0,maxAltTime)
        axs[0, 2].legend()

        # Volume vs Time
        axs[1, 2].plot(time, flyParameters["s1_airVolume"], label="s1 air volume")
        axs[1, 2].plot(time, flyParameters["s2_airVolume"], label="s2 air volume")
        axs[1, 2].plot(time, flyParameters["s1_waterVolume"], label="s1 water volume")
        axs[1, 2].plot(time, flyParameters["s2_waterVolume"], label="s2 water volume")
        axs[1, 2].set_title("Volume vs Time")
        axs[1, 2].set_xlabel("Time (s)")
        axs[1, 2].set_ylabel("Volume")
        axs[1, 2].grid()
        axs[1, 2].set_xlim(0,maxAltTime)
        axs[1, 2].legend()

        # Thrust mode vs Time
        axs[2, 2].plot(time, flyParameters["s1_thrustMode"], label="s1_thrustMode")
        axs[2, 2].plot(time, flyParameters["s2_thrustMode"]+4, label="s2_thrustMode")
        axs[2, 2].set_title("Thurst mode")
        axs[2, 2].set_xlabel("Time (s)")
        axs[2, 2].set_ylabel("Mode")
        axs[2, 2].grid()
        axs[2, 2].set_xlim(0,maxAltTime)
        axs[2, 2].legend()

        s1waterMassVariation = flyParameters["s1_waterMass"] - np.concatenate( (np.array([flyParameters["s1_waterMass"][0]]),flyParameters["s1_waterMass"][:-1]))
        # Cumulative sum of mass variation
        s1CumulMassVariation = -1 * np.cumsum(s1waterMassVariation)
        s2waterMassVariation = flyParameters["s2_waterMass"] - np.concatenate( (np.array([flyParameters["s2_waterMass"][0]]),flyParameters["s2_waterMass"][:-1]))
        # Cumulative sum of mass variation
        s2CumulMassVariation = -1 * np.cumsum(s2waterMassVariation)

        # Mass variation vs Time
        #axs[2, 1].plot(time, s1CumulMassVariation, label="S1 cumulative mass variation")
        #axs[2, 1].plot(time, s2CumulMassVariation, label="S2 cumulative mass variation")
        axs[2, 1].plot(time, flyParameters["s1_waterExpulsionMassFlow"], label="S1 water mass flow")
        axs[2, 1].plot(time, flyParameters["s2_waterExpulsionMassFlow"], label="S2 water mass flow")
        axs[2, 1].plot(time, flyParameters["s1_airExpulsionMassFlow"], label="S1 air mass flow")
        axs[2, 1].plot(time, flyParameters["s2_airExpulsionMassFlow"], label="S2 air mass flow")
        axs[2, 1].set_title("Mass flow vs Time")
        axs[2, 1].set_xlabel("Time (s)")
        axs[2, 1].set_ylabel("Mass (Kg)")
        axs[2, 1].grid()
        axs[2, 1].set_xlim(0,maxAltTime)
        axs[2, 1].legend()

        plt.tight_layout()
        fig.canvas.manager.full_screen_toggle()  # Toggle fullscreen once
        plt.show()

    def plot_altitudeVsTime(self,
                            flyParameters):
        """Plot the altitude of the rocket over time.

        Args:
            flyParameters (dict): Simulation results dictionary returned by :meth:`launchSimulation`.
        """
        plt.figure(figsize=(10, 6))
        plt.plot(np.arange(0, simulationTime(flyParameters) + simulationStep(flyParameters), simulationStep(flyParameters)), flyParameters["rocket_altitude"], label='Rocket Altitude', color='blue')
        plt.title('Rocket Altitude vs Time')
        plt.xlabel('Time (s)')
        plt.ylabel('Altitude (m)')
        plt.grid()
        plt.legend()
        plt.show()

    def animate_rocket_launch(self,
                              flyParameters):
        """Animate the rocket launch using Pygame.

        Args:
            flyParameters (dict): Simulation results dictionary returned by :meth:`launchSimulation`.
        """
        # Pygame setup
        pygame.init()
        width, height = 400, 600
        screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Water Rocket Launch Animation")
        clock = pygame.time.Clock()

        # Rocket drawing parameters
        rocket_width = 30
        rocket_height = 80
        ground_y = height - 50

        # Get altitude data
        altitudes = flyParameters["rocket_altitude"]
        max_altitude = np.max(altitudes)
        times = flyParameters["time"]
        n_frames = len(times)

        # Scale altitude to screen
        def altitude_to_y(alt):
            # 0 altitude -> ground_y, max_altitude -> 50 px from top
            if max_altitude == 0:
                return ground_y
            return int(ground_y - (alt / max_altitude) * (ground_y - 50))

        # Animation loop
        running = True
        frame = 0
        while running:
            clock.tick(60)  # 60 FPS
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Clear screen
            screen.fill((135, 206, 235))  # Sky blue

            # Draw ground
            pygame.draw.rect(screen, (34, 139, 34), (0, ground_y, width, height - ground_y))

            # Draw rocket
            y = altitude_to_y(altitudes[frame])
            rocket_rect = pygame.Rect(width // 2 - rocket_width // 2, y, rocket_width, rocket_height)
            pygame.draw.rect(screen, (200, 200, 200), rocket_rect)  # Rocket body
            pygame.draw.polygon(screen, (255, 0, 0), [
                (rocket_rect.centerx, y - 20),
                (rocket_rect.left, y),
                (rocket_rect.right, y)
            ])  # Nose cone

            # Draw flame if thrust > 0
            thrust = flyParameters["total_thrust"][frame]
            if thrust > 1:
                flame_height = min(40, int(thrust / 20))
                flame_color = (255, 140, 0)
                pygame.draw.polygon(screen, flame_color, [
                    (rocket_rect.centerx, rocket_rect.bottom),
                    (rocket_rect.centerx - 10, rocket_rect.bottom + flame_height),
                    (rocket_rect.centerx + 10, rocket_rect.bottom + flame_height)
                ])

            # Draw info
            font = pygame.font.SysFont(None, 24)
            text = font.render(f"Time: {times[frame]:.2f}s  Altitude: {altitudes[frame]:.2f}m", True, (0, 0, 0))
            screen.blit(text, (10, 10))

            pygame.display.flip()

            # Advance frame
            if frame < n_frames - 1:
                frame += 1
            else:
                pygame.time.wait(1500)
                running = False

        pygame.quit()
        sys.exit()

    def plot_altitude_and_thrust(self,
                                 flyParameters):
        """Plot altitude and total thrust versus time on dual y-axes.

        Args:
            flyParameters (dict): Simulation results dictionary returned by :meth:`launchSimulation`.
        """
        time = flyParameters["time"]
        altitude = flyParameters["rocket_altitude"]
        thrust = flyParameters["total_thrust"]

        # determine simulation step
        dt = (time[1] - time[0]) if len(time) > 1 else 0.01

        # find time to end: when rocket has lost 10 m after max altitude
        max_idx = int(np.argmax(altitude))
        max_alt = altitude[max_idx]
        loss_threshold = max_alt - 10.0

        # search for first index after max_idx where altitude <= loss_threshold
        post_mask = (np.arange(len(altitude)) > max_idx) & (altitude <= loss_threshold)
        post_indices = np.where(post_mask)[0]
        if post_indices.size > 0:
            end_idx = post_indices[0]
            end_time = time[end_idx] + dt
        else:
            # fallback: use last time value
            end_time = time[-1]

        fig, ax1 = plt.subplots(figsize=(10, 5))

        color_alt = "tab:blue"
        ax1.set_xlabel("Temps (s)")
        ax1.set_ylabel("Altitude (m)", color=color_alt)
        ax1.plot(time, altitude, color=color_alt, label="Altitude")
        ax1.tick_params(axis="y", labelcolor=color_alt)
        ax1.grid(True)
        ax1.set_xlim(0, end_time)

        ax2 = ax1.twinx()
        color_thrust = "tab:red"
        ax2.set_ylabel("Poussée Totale (N)", color=color_thrust)
        ax2.plot(time, thrust, color=color_thrust, label="Poussée Totale")
        ax2.tick_params(axis="y", labelcolor=color_thrust)
        ax2.set_xlim(0, end_time)

        # combined legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

        plt.title("Altitude et Poussée Totale vs Temps")
        plt.tight_layout()
        plt.show()

    def save_flyparameters_to_csv(self,
                                  flyParameters,
                                  filename="rocket_simulation.csv"):
        """Save simulation results to a CSV file.

        Args:
            flyParameters (dict): Dictionary containing the simulation results.
            filename (str): Path to the CSV file to write.
        """
        
        # Create a DataFrame from flyParameters
        df = pd.DataFrame(flyParameters)
        
        # Save to Excel
        df.to_csv(filename)
        
        print(f"Simulation results saved to {filename}")
