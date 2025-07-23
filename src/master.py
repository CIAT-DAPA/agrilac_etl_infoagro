from datetime import datetime, timedelta
from imerg_data import IMERGData
from mswx_data import MSWXData
from tools import Tools
import os, sys

class Master:
    #Today date for use in folders
    TODAY = datetime.now().date().strftime('%Y%m%d')
    INI_DATE = ""
    FIN_DATE = ""
    WORSKPACE = ""
    CONFIG_FOLDER = ""
    INPUTS_FOLDER = ""
    OUTPUTS_FOLDER = ""
    INPUTS_DOWNLOADED_DATA=""
    INPUTS_FORECAST_DATA=""
    HONDURAS_SHP_PATH=""
    HONDURAS_REGIONS_PATH=""
    HONDURAS_MUNICIPALITIES_PATH=""


    def __init__(self, central_date, workspace_path=None, path_shp_crop_honduras=None, 
                 path_shp_crop_honduras_regions=None, path_shp_crop_honduras_municipalities=None, path_forecast_files=None):
        """
        Inicializa la clase con los parametros del usuario, así como también la construcción de los diferentes directorios.
        """
        self.WORKSPACE = workspace_path if workspace_path is not None else "../workspace/"
        self.CONFIG_FOLDER = os.path.join(self.WORKSPACE, "config/")
        self.INPUTS_FOLDER = os.path.join(self.WORKSPACE, "input/")
        self.OUTPUTS_FOLDER = os.path.join(self.WORKSPACE, "output/")
        self.INPUTS_DOWNLOADED_DATA = os.path.join(self.INPUTS_FOLDER, "downloaded_data/")
        self.INPUTS_FORECAST_DATA = path_forecast_files if path_forecast_files is not None else os.path.join(self.INPUTS_FOLDER, "forecast_data/")
        self.HONDURAS_SHP_PATH = path_shp_crop_honduras if path_shp_crop_honduras is not None else os.path.join(self.CONFIG_FOLDER, "mask_honduras/")
        self.HONDURAS_REGIONS_PATH = path_shp_crop_honduras_regions if path_shp_crop_honduras_regions is not None else os.path.join(self.HONDURAS_SHP_PATH, "regions_shapefile/")
        self.HONDURAS_MUNICIPALITIES_PATH = path_shp_crop_honduras_municipalities if path_shp_crop_honduras_municipalities is not None else os.path.join(self.HONDURAS_SHP_PATH, "municipalities_shapefile/")

        self.FIN_DATE = datetime.strptime(central_date, "%Y-%m-%d").date()
        self.INI_DATE = self.FIN_DATE - timedelta(days=10)

        print("fecha de inicio: ", self.INI_DATE)
        print("fecha de fin: ",self.FIN_DATE)
    

    """
    MSXW data process
    """
    def run_mswx_data_proccess(self, ini_date, fin_date):
        tools = Tools()
        print("Creando archivo credentials.json a partir de las variables de entorno...")
        tools.create_gcc_json(f"{self.CONFIG_FOLDER}credentials.json")
        credentials_file = os.path.join(f"{self.CONFIG_FOLDER}credentials.json")
        folder_id = "14no0Wkoat3guyvVnv-LccXOEoxQqDRy7"  
        
        var_mswx = {
            "Tmax": "Tmax_variable_id",
            "Tmin": "Tmin_variable_id",
            "RelHum": "RelHum_variable_id",
            "Wind": "Wind_variable_id",
            "SWd": "SWd_variable_id",
            "Temp": "Temp_variable_id"
        }

        google_drive_mswx = MSWXData(credentials_file)
        folders = google_drive_mswx.list_folders_in_folder(folder_id, var_mswx)

        for folder in folders:
            google_drive_mswx.list_files_in_daily_folder(folder['id'], ini_date, fin_date, os.path.join(f"{self.INPUTS_DOWNLOADED_DATA}{self.TODAY}"), folder['title'])

        google_drive_mswx.calculate_et0(ini_date, fin_date, inputdatapath=os.path.join(f"{self.INPUTS_DOWNLOADED_DATA}{self.TODAY}/MSWX/"), outputpath=os.path.join(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/"), mask_file_path=f'{self.HONDURAS_SHP_PATH}mask_mswx_hnd.nc4')

    """
    IMERG data process
    """  
    def run_imerg_data_process(self, ini_date, fin_date):
        imerg_process = IMERGData()
        try:
            imerg_process.imerg(ini_date, fin_date, os.path.join(f"{self.INPUTS_DOWNLOADED_DATA}{self.TODAY}/IMERG/"), os.path.join(f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/"), mask_file_path=f'{self.HONDURAS_SHP_PATH}mask_mswx_hnd.nc4')
        except:
            print("Error al crear archivo IMERG_Honduras.nc de precipitación observada. Revisar si la descarga de IMERG fue correcta y se creó el archivo IMERG_Honduras.nc")
        
#python src\master.py "2025-06-05" D:\Code\Honduras\wrf None None None D:\Code\Honduras\wrf\output\postprocessing\wrfout_d01_2025-06-05.nc
    """
    Post data process
    """
    def post_data_process(self, ini_date, fin_date):
        tools = Tools()
        
        # Check if MSWX data is available
        mswx_temp_path = f"{self.INPUTS_DOWNLOADED_DATA}{self.TODAY}/MSWX/Temp/"
        mswx_et0_path = f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/ET0_Honduras.nc"
        mswx_available = os.path.exists(mswx_temp_path) and os.path.exists(mswx_et0_path)
        
        # Check if IMERG data is available
        imerg_path = f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/IMERG_Honduras.nc"
        imerg_available = os.path.exists(imerg_path)
        
        print(f"MSWX data available: {mswx_available}")
        print(f"IMERG data available: {imerg_available}")

        # Process MSWX temperature data if available
        if mswx_available:
            try:
                print("Translating julian dates for MSWX temperature data...")
                tools.translate_julian_dates(mswx_temp_path)
                print("Julian dates translation completed.")
            except Exception as e:
                print(f"Error translating julian dates: {e}")
                mswx_available = False

            # Merge temperature files if MSWX data is available
            try:
                print("Merging MSWX temperature files...")
                tools.merge_files(ini_date, fin_date, mswx_temp_path, f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp.nc", "nc", "grados celcius", variable_name='air_temperature')
                print("MSWX temperature files merged successfully.")
            except Exception as e:
                print(f"Error merging MSWX temperature files: {e}")
                mswx_available = False

            # Crop observed temperature for Honduras if MSWX merge was successful
            if mswx_available:
                try:
                    print("Cropping observed Temp for Honduras...")
                    tools.country_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp.nc", f"{self.HONDURAS_SHP_PATH}mask_mswx_hnd.nc4", f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp_Honduras.nc")
                    print(f"Cropped Temp saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/")
                    print("Cropping observed Temp for Honduras completed.")
                except Exception as e:
                    print(f"Error cropping observed temperature: {e}")
                    mswx_available = False
        else:
            print("MSWX data not available. Skipping MSWX temperature processing.")

        # Process forecast data if available
        print(self.INPUTS_FORECAST_DATA)
        if os.path.exists(self.INPUTS_FORECAST_DATA) and os.listdir(self.INPUTS_FORECAST_DATA):
            print("Processing forecast data for each domain...")
            
            # Process each domain folder
            for carpeta in os.listdir(self.INPUTS_FORECAST_DATA):
                partes = carpeta.split("_")
                # Luego, podemos concatenar las partes necesarias para obtener "wrfout_d02_2024-0"
                subcadena = partes[0] + "_" + partes[1] + "_" + partes[2][:7]
                ruta_dominio_actual = os.path.join(self.INPUTS_FORECAST_DATA, carpeta)
                
                if os.path.isdir(ruta_dominio_actual):  # Verifica que sea una carpeta
                    print(f"Processing domain: {carpeta}")
                    print("Merging forecast files...")
                    
                    try:
                        # Merge forecast files
                        tools.merge_files(fin_date, fin_date + timedelta(days=10), f"{ruta_dominio_actual}/RAIN/RAIN_", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_RAIN_forecast_Honduras.nc", "tif", "mm/day", variable_name='precipitation')
                        tools.merge_files(fin_date, fin_date + timedelta(days=10), f"{ruta_dominio_actual}/ET0/ET0_", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_ET0_forecast_Honduras.nc", "tif", "mm/day", variable_name='ET0')
                        tools.merge_files(fin_date, fin_date + timedelta(days=10), f"{ruta_dominio_actual}/T2/T2_", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_Temperature_forecast_Honduras.nc", "tif", "grados celcius", variable_name='air_temperature')
                        print(f"Merged files saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/forecast/")
                        print("Merging forecast files completed.")
                    except Exception as e:
                        print(f"Error merging forecast files for domain {carpeta}: {e}")
                        continue

                    # Crop regions (only process those that have dependencies satisfied)
                    print("Cropping regions...")
                    try:
                        # Always process forecast regions (no dependency)
                        tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_ET0_forecast_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_ET0_forecast_Honduras_regions.nc", "Nombre")
                        tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_RAIN_forecast_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_RAIN_forecast_Honduras_regions.nc", "Nombre")
                        tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_Temperature_forecast_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_Temperature_forecast_Honduras_regions.nc", "Nombre")
                        
                        # Process MSWX regions only if MSWX data is available
                        if mswx_available:
                            tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/ET0_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/ET0_Honduras_regions.nc", "Nombre")
                            tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp_Honduras_regions.nc", "Nombre")
                            print(f"MSWX regions cropped and saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/")
                        else:
                            print("MSWX data not available. Skipping MSWX region cropping.")
                        
                        # Process IMERG regions only if IMERG data is available
                        if imerg_available:
                            tools.regions_crop(f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/IMERG_Honduras.nc", f"{self.HONDURAS_REGIONS_PATH}Regiones_productoras_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/IMERG_Honduras_regions.nc", "Nombre")
                            print(f"IMERG regions cropped and saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/")
                        else:
                            print("IMERG data not available. Skipping IMERG region cropping.")
                        
                        print(f"Forecast regions cropped and saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/forecast/")
                        print("Cropping regions completed.")
                    except Exception as e:
                        print(f"Error cropping regions for domain {carpeta}: {e}")

                    # Plot files (only plot those with available data)
                    print("Plotting files...")
                    try:
                        # Plot MSWX files only if available
                        if mswx_available:
                            tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp_Honduras_regions.nc", "air_temperature", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/temperature_honduras_observado_")
                            tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/ET0_Honduras_regions.nc", "ET0", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/et0_honduras_observado_")
                            print("MSWX plots generated successfully.")
                        else:
                            print("MSWX data not available. Skipping MSWX plotting.")
                        
                        # Plot IMERG files only if available
                        if imerg_available:
                            tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/IMERG_Honduras_regions.nc", "precipitation", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/precipitation_honduras_observado_")
                            print("IMERG plots generated successfully.")
                        else:
                            print("IMERG data not available. Skipping IMERG plotting.")
                        
                        # Always plot forecast files (no dependency)
                        tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_Temperature_forecast_Honduras_regions.nc", "air_temperature", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/{subcadena}_temperature_honduras_forecast_")
                        tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_ET0_forecast_Honduras_regions.nc", "ET0", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/{subcadena}_et0_honduras_forecast_")
                        tools.plot_nc_file(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_RAIN_forecast_Honduras_regions.nc", "precipitation", save_path=f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/{subcadena}_precipitation_honduras_forecast_")
                        
                        print(f"Plot files saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/figures/")
                        print("Plotting files completed.")
                    except Exception as e:
                        print(f"Error plotting files for domain {carpeta}: {e}")

                    # Generate CSV for daily mean per municipality (only with available data)
                    print("Writing CSV file for daily mean for municipalities...")
                    try:
                        dataframes_to_merge = []
                        
                        # Process MSWX data only if available
                        if mswx_available:
                            temp = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/Temp_Honduras.nc", "air_temperature", "NAME_1", "NAME_2", "c", "air-temperature_obs")
                            et0_mswx = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/MSWX/ET0_Honduras.nc", "ET0", "NAME_1", "NAME_2", "mm-day", "et0_obs")
                            dataframes_to_merge.extend([temp, et0_mswx])
                            print("MSWX municipality data calculated successfully.")
                        else:
                            print("MSWX data not available. Skipping MSWX municipality calculations.")
                        
                        # Process IMERG data only if available
                        if imerg_available:
                            prep_imerg = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/IMERG/IMERG_Honduras.nc", "precipitation", "NAME_1", "NAME_2", "mm-day", "precipitation-cal_obs")
                            dataframes_to_merge.append(prep_imerg)
                            print("IMERG municipality data calculated successfully.")
                        else:
                            print("IMERG data not available. Skipping IMERG municipality calculations.")
                        
                        # Always process forecast data (no dependency)
                        temp_forecast = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_Temperature_forecast_Honduras.nc", "air_temperature", "NAME_1", "NAME_2", "c", "air-temperature_for")
                        et0_forecast = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_ET0_forecast_Honduras.nc", "ET0", "NAME_1", "NAME_2", "mm-day", "et0_for")
                        prep_forecast = tools.calculate_daily_mean_per_municipality(f"{self.HONDURAS_MUNICIPALITIES_PATH}Municipios_reg_prod_HN.shp", f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/{carpeta}_RAIN_forecast_Honduras.nc", "precipitation", "NAME_1", "NAME_2", "mm-day", "precipitation-cal_for")
                        dataframes_to_merge.extend([temp_forecast, et0_forecast, prep_forecast])

                        # Merge all available dataframes
                        if len(dataframes_to_merge) >= 2:
                            merged_df = dataframes_to_merge[0]
                            for df in dataframes_to_merge[1:]:
                                merged_df = merged_df.merge(df, on=["region", "municipio"])
                            
                            merged_df.to_csv(f"{self.OUTPUTS_FOLDER}{self.TODAY}/{carpeta}_daily_mean_municipalities.csv", index=False, encoding='utf-8-sig')
                            print(f"CSV file for daily mean for municipalities saved on: {self.OUTPUTS_FOLDER}{self.TODAY}/{carpeta}_daily_mean_municipalities.csv")
                            print("Writing CSV file for daily mean for municipalities completed.")
                        else:
                            print("Insufficient data to generate municipality CSV. At least forecast data is required.")
                            
                    except Exception as e:
                        print(f"Error writing CSV file for domain {carpeta}: {e}")
                        
                    print(f"Domain {carpeta} processing completed.")
        else:
            print("No forecast data available. Skipping forecast processing.")


    def creates_folders(self):
           #Creates output forecast and figures folders
        if not os.path.exists(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/"):
            os.makedirs(f"{self.OUTPUTS_FOLDER}{self.TODAY}/forecast/")
        if not os.path.exists(f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/"):
            os.makedirs(f"{self.OUTPUTS_FOLDER}{self.TODAY}/figures/")

if __name__ == "__main__":
    variable = os.getenv('ETL_EXEC')

    if variable is None or bool(int(variable)):
      
        def process_arg(arg):
            return None if arg == 'None' or arg is None else arg

        # Procesar los argumentos
        #YYYY-MM-DD
        central_date = sys.argv[1] if len(sys.argv) > 1 else None
        workspace_path = process_arg(sys.argv[2]) if len(sys.argv) > 2 else None
        path_shp_crop_honduras = process_arg(sys.argv[3]) if len(sys.argv) > 3 else None
        path_shp_crop_honduras_regions = process_arg(sys.argv[4]) if len(sys.argv) > 4 else None
        path_shp_crop_honduras_municipalities = process_arg(sys.argv[5]) if len(sys.argv) > 5 else None
        path_forecast_files = process_arg(sys.argv[6]) if len(sys.argv) > 6 else None

        main = Master(central_date, workspace_path, path_shp_crop_honduras, path_shp_crop_honduras_regions, path_shp_crop_honduras_municipalities, path_forecast_files)
        main.creates_folders()

        # Check for IMERG environment variables
        imerg_user = os.getenv('IMERG_USERNAME')
        imerg_pass = os.getenv('IMERG_PWD')

        # Check for MSWX environment variables (Google Drive credentials)
        gcc_variables = [
            "GCC_TYPE",
            "GCC_PROJECT_ID", 
            "GCC_PRIVATE_KEY_ID",
            "GCC_PRIVATE_KEY",
            "GCC_CLIENT_EMAIL",
            "GCC_CLIENT_ID",
            "GCC_AUTH_URI",
            "GCC_TOKEN_URI",
            "GCC_AUTH_PROVIDER_X509_CERT_URL",
            "GCC_CLIENT_X509_CERT_URL",
            "GCC_UNIVERSE_DOMAIN"
        ]
        
        gcc_data = {}
        mswx_credentials_available = True
        
        try:
            for var in gcc_variables:
                var = os.getenv(var)
                if var is None:
                    mswx_credentials_available = False
                    break
                gcc_data[var.lower()] = var
        except Exception:
            mswx_credentials_available = False
        
        if imerg_user and imerg_pass:
            print("IMERG data process begin...")
            main.run_imerg_data_process(main.INI_DATE, main.FIN_DATE)
            print("IMERG data process end.")
        else:
            print("IMERG credentials not found. Skipping IMERG data process.")
            
        if mswx_credentials_available:
            print("MSWX data process begin...")
            main.run_mswx_data_proccess(main.INI_DATE, main.FIN_DATE)
            print("MSWX data process end.")
        else:
            print("MSWX credentials not found. Skipping MSWX data process.")

        main.post_data_process(main.INI_DATE, main.FIN_DATE)
    