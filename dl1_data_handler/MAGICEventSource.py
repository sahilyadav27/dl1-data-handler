from ctapipe.io.eventsource import EventSource
import uproot
from ctapipe.io.containers import DataContainer, TelescopePointingContainer
from ctapipe.instrument import TelescopeDescription, SubarrayDescription, OpticsDescription, CameraGeometry
import glob
import re
import numpy as np
from astropy import units as u
from astropy.coordinates import Angle
X_MAX_UNIT = u.g / (u.cm ** 2)
class MAGICEventSource(EventSource):
    def __init__(self, **kwargs):
        """
        Constructor
        
        Parameters
        ----------
        kwargs: dict
            Parameters to be passed.
            NOTE: The file mask of the data to read can be passed with
            the 'input_url' parameter.
        """
        self.file_list = glob.glob(kwargs['input_url'])
        self.file_list.sort()

        # Since EventSource can not handle file wild cards as input_url
        # We substitute the input_url with first file matching
        # the specified file mask.
        
        del kwargs['input_url']
        super().__init__(input_url=self.file_list[0], **kwargs)
        
        # get run number
        mask = r".*_M\d_za\d+to\d+_\d_(\d+)_Y_.*"
        parsed_info = re.findall(mask, self.file_list[0])
        self.run_number = parsed_info[0]
        
        # MAGIC telescope positions in m wrt. to the center of CTA simulations

        self.magic_tel_positions = {
            1: [-27.24, -146.66, 50.00] * u.m,
            2: [-96.44, -96.77, 51.00] * u.m
        }
        self.magic_tel_positions = self.magic_tel_positions
        # MAGIC telescope description
        optics = OpticsDescription.from_name('MAGIC')
        geom = CameraGeometry.from_name('MAGICCam')
        self.magic_tel_description = TelescopeDescription(name='MAGIC', tel_type = 'LST', optics=optics, camera=geom)
        self.magic_tel_descriptions = {1: self.magic_tel_description, 2: self.magic_tel_description}
        self.magic_subarray = SubarrayDescription('MAGIC', self.magic_tel_positions, self.magic_tel_descriptions)
        file1 = uproot.open(self.file_list[0])
        self.eventM1 = file1["Events"]
        file2 = uproot.open(self.file_list[1])
        self.eventM2 = file2["Events"]
        
    @staticmethod
    def is_compatible(file_mask):
        """
        This method checks if the specified file mask corresponds
        to MAGIC data files. The result will be True only if all
        the files are of ROOT format and contain an 'Events' tree.
        Parameters
        ----------
        file_mask: str
            A file mask to check
        Returns
        -------
        bool:
            True if the masked files are MAGIC data runs, False otherwise.
        """

        is_magic_root_file = True

        file_list = glob.glob(file_mask)

        for file_path in file_list:
            try:
                import uproot

                try:
                    with uproot.open(file_path) as input_data:
                        if 'Events' not in input_data:
                            is_magic_root_file = False
                except ValueError:
                    # uproot raises ValueError if the file is not a ROOT file
                    is_magic_root_file = False
                    pass

            except ImportError:
                if re.match(r'.+_m\d_.+root', file_path.lower()) is None:
                    is_magic_root_file = False

        return is_magic_root_file  

    def _generator(self):
        """
        Stereo event generator. Yields DataContainer instances, filled
        with the read event data.
        
        Returns
        -------
        
        """  
        counter = 0
        data = DataContainer()
        data.meta['origin'] = "MAGIC"
        data.meta['input_url'] = self.input_url
        data.meta['is_simulation'] = True
        
        #Reading data from root file for Events table
        eventidM1 = np.asarray(self.eventM1["MRawEvtHeader.fStereoEvtNumber"].array())
        eventidM2 = np.asarray(self.eventM2["MRawEvtHeader.fStereoEvtNumber"].array())
        
        zenith = np.asarray(self.eventM1["MMcEvt.fTheta"].array())
        
        pointing_altitude = np.asarray(self.eventM1["MPointingPos.fZd"].array())
        
        azimuth = np.asarray(self.eventM1["MMcEvt.fPhi"].array())
        
        pointing_azimuth = np.asarray(self.eventM1["MPointingPos.fAz"].array())
        
        core_x = np.asarray(self.eventM1["MMcEvt.fCoreX"].array())
        core_y = np.asarray(self.eventM1["MMcEvt.fCoreY"].array())
        
        mc_energy = np.asarray(self.eventM1["MMcEvt.fEnergy"].array())/1000
        h_first_int = np.asarray(self.eventM1["MMcEvt.fZFirstInteraction"].array())
        
        mask = r".([A-Z]+)_M\d_za\d+to\d+_\d_\d+_Y_.*"
        primary_id = re.findall(mask, self.file_list[0])[0]
        if primary_id == 'GA':
            shower_primary_id = 1
            
        stereo_total = np.max(eventidM1)
        event_index = np.zeros(shape = (stereo_total,1))
        
        #Reading data from root file for Image table
        
        chargeM1 = self.eventM1["MCerPhotEvt.fPixels.fPhot"].array()
        pulse_timeM1 = self.eventM1["MArrivalTime.fData"].array()
        chargeM1 = np.asarray(chargeM1)
        pulse_timeM1 = np.asarray(pulse_timeM1)
        
        chargeM2 = self.eventM2["MCerPhotEvt.fPixels.fPhot"].array()
        pulse_timeM2 = self.eventM2["MArrivalTime.fData"].array()
        chargeM2 = np.asarray(chargeM2)
        pulse_timeM2 = np.asarray(pulse_timeM2)
        
        total_events = len(self.eventM1["MCerPhotEvt.fPixels.fPhot"].array())
        #Iterating over all events, and saving only stereo ones
        tels_in_file = ["m1", "m2"]
        tels_with_data = {1,2}
        for i in range(0, total_events):
            if eventidM1[i] != 0:
                obs_id = self.run_number
                event_id = eventidM1[i]
                i2 = np.where(eventidM2==eventidM1[i])
                i2 = int(i2[0])
                data.count = counter
                # Setting up the R0 container
                data.r0.obs_id = obs_id
                data.r0.event_id = event_id
                data.r0.tel.clear()

                # Setting up the R1 container
                data.r1.obs_id = obs_id
                data.r1.event_id = event_id
                data.r1.tel.clear()
                
                # Setting up the DL0 container
                data.dl0.obs_id = obs_id
                data.dl0.event_id = event_id
                data.dl0.tel.clear()
                
                # Filling the DL1 container with the event data
                for tel_i, tel_id in enumerate(tels_in_file):
                    
                    #Creating telescope pointing container
                    pointing = TelescopePointingContainer()
                    pointing.azimuth = u.Quantity(np.deg2rad(pointing_azimuth[i]), u.rad)
                    pointing.altitude = u.Quantity(np.deg2rad(90 - pointing_altitude[i]), u.rad)
                    
                    # Adding pointing container to event data
                    data.pointing[tel_i+1] = pointing
                    
                    #Adding MC data
                    data.mc.alt = Angle(zenith[i], u.rad)
                    data.mc.az = Angle(azimuth[i], u.rad)
                    data.mc.x_max = u.Quantity(0, X_MAX_UNIT)
                    data.mc.h_first_int = u.Quantity(h_first_int[i], u.m)
                    data.mc.core_x = u.Quantity(core_x[i], u.m)
                    data.mc.core_y = u.Quantity(core_y[i], u.m)
                    data.mc.energy = u.Quantity(mc_energy[i], u.TeV)
                    data.mc.shower_primary_id = shower_primary_id
                    # Adding event charge and peak positions per pixel
                    if tel_i == 0:
                        data.dl1.tel[tel_i + 1].image = chargeM1[i][:1039]
                        data.dl1.tel[tel_i + 1].pulse_time = pulse_timeM1[i][:1039]
                    else:
                        data.dl1.tel[tel_i + 1].image = chargeM2[i][:1039]
                        data.dl1.tel[tel_i + 1].pulse_time = pulse_timeM2[i][:1039]                      
                
                # Setting the telescopes with data
                data.r0.tels_with_data = tels_with_data
                data.r1.tels_with_data = tels_with_data
                data.dl0.tels_with_data = tels_with_data
                data.trig.tels_with_trigger = tels_with_data

                # Setting the instrument sub-array
                data.inst.subarray = self.magic_subarray

                yield data
                counter += 1
        return