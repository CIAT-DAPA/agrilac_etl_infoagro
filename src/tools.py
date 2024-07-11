import os
import xarray as xr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import timedelta, datetime
import cftime
import geopandas as gpd
import rasterio
from shapely.geometry import mapping
import cartopy.crs as ccrs
import cartopy.feature as cfeature

class Tools():

    def plot_nc_file(self, file_path, variable_name, save_path, lon_dim='lon', lat_dim='lat', time_dim='time'):
        """
        Función para graficar el promedio diario y la desviación estándar de una variable en un archivo NetCDF y guardar la figura.

        Parámetros:
        - file_path: Ruta al archivo NetCDF.
        - variable_name: Nombre de la variable a graficar.
        - save_path: Ruta donde se guardará la figura.
        - lon_dim: Nombre de la dimensión de longitud (por defecto 'lon').
        - lat_dim: Nombre de la dimensión de latitud (por defecto 'lat').
        - time_dim: Nombre de la dimensión de tiempo (por defecto 'time').
        """
        # Abrir el archivo NetCDF
        dataset = xr.open_dataset(file_path)

        # Verificar si la variable existe en el conjunto de datos
        if variable_name not in dataset:
            raise ValueError(f"La variable '{variable_name}' no se encuentra en el archivo.")

        # Calcular el promedio diario y la desviación estándar
        daily_mean = dataset[variable_name].mean(dim=[lon_dim, lat_dim])
        daily_std = dataset[variable_name].std(dim=[lon_dim, lat_dim])

        # Extraer los datos de tiempo
        time = dataset[time_dim].values

        # Convertir el tiempo de cftime.DatetimeGregorian a pandas datetime
        if isinstance(time[0], cftime.DatetimeGregorian):
            time = np.array([np.datetime64(date.strftime('%Y-%m-%d')) for date in time])

        # Calcular los rangos de incertidumbre
        upper_bound = daily_mean + daily_std
        lower_bound = daily_mean - daily_std

        # Obtener las unidades de la variable
        units = dataset[variable_name].attrs.get('units', 'unidades')

        # Graficar
        plt.figure(figsize=(10, 6))
        plt.plot(time, daily_mean, label=f'{variable_name} promedio', color='green')
        plt.fill_between(time, lower_bound, upper_bound, color='green', alpha=0.3, label='Rango de incertidumbre')
        plt.xlabel('Días')
        plt.ylabel(f'{variable_name} ({units})')
        plt.title(f'Promedio diario de {variable_name} con rango de incertidumbre')
        plt.legend()
        plt.grid(True)

        # Guardar la figura
        plt.savefig(f"{save_path}{variable_name}")
        plt.close()
    
    def country_crop(self, file_to_be_cropped, mask_file, output_file):
        
        file_to_be_cropped = xr.open_dataset(file_to_be_cropped)
        mask_file = mask_file
        ds_mask = xr.open_dataset(mask_file)

        # Aplicar la máscara a los datos globales
        ds_global_honduras = file_to_be_cropped.where(ds_mask['mask'] == 1, drop=True)
        ds_global_honduras.to_netcdf(output_file)

        ds_mask.close()

    
    def regions_crop(self, file_to_be_cropped, shapefile, output_file, name_column):
        # Abre el archivo netCDF
        ds = xr.open_dataset(file_to_be_cropped, decode_times=False)
        print(ds)

        # Asegúrate de que el dataset tenga las coordenadas necesarias para rioxarray
        if 'crs' not in ds.attrs:
            ds.rio.write_crs("EPSG:4326", inplace=True)  # Ajusta el EPSG según sea necesario

         # Obtener las dimensiones del archivo NetCDF
        lon_dim = 'lon' if 'lon' in ds.dims else 'x'
        lat_dim = 'lat' if 'lat' in ds.dims else 'y'


        # Configura las dimensiones espaciales
        ds = ds.rio.set_spatial_dims(x_dim=lon_dim, y_dim=lat_dim, inplace=True)

        # Abre el shapefile usando geopandas
        regions = gpd.read_file(shapefile)

        # Asegúrate de que el shapefile y el netCDF tengan el mismo sistema de coordenadas
        if ds.rio.crs != regions.crs:
            regions = regions.to_crs(ds.rio.crs)

        # Obtener la primera variable de datos del dataset
        data_var = list(ds.data_vars.keys())[0]

        # Crear una lista para almacenar los datasets recortados
        clipped_datasets = []
        # Crear una lista para almacenar los nombres de las regiones
        region_names = []

        # Iterar sobre cada región y recortar el dataset
        for idx, region in regions.iterrows():
            geometry = [mapping(region.geometry)]
            
            # Crear la máscara de la región
            mask = ds.rio.clip(geometry, drop=False)
            
            # Asegurarse de que la máscara tenga las mismas dimensiones que el dataset original
            mask = mask[data_var].notnull().astype(int)

            # Crear una variable para la región con un nombre único basado en el nombre de la columna
            region_name = region[name_column]
            region_masked = xr.where(mask, ds[data_var], float('nan'))

            # Añadir el dataset recortado a la lista
            clipped_datasets.append(region_masked)
            region_names.append(region_name)

        # Combinar todos los datasets recortados en uno solo
        combined_ds = xr.concat(clipped_datasets, dim='region')
        combined_ds = combined_ds.assign_coords(region=region_names)

        # Guardar el resultado en un nuevo archivo netCDF
        combined_ds.to_netcdf(output_file)

        return output_file

    def merge_files(self, start_date, end_date, data_folder, output_folder, file_type, units, variable_name='data'):
        # Generar la lista de fechas
        date_range = pd.date_range(start=start_date, end=end_date - timedelta(days=1))

        # Crear una lista para almacenar los datasets
        datasets = []
        times = []

        for date in date_range:
            year = date.year
            month = str(date.month).zfill(2)
            day = str(date.day).zfill(2)

            # Construir el nombre del archivo
            filename = f'{data_folder}{year}-{month}-{day}.{file_type}'

            # Verificar si el archivo existe
            if os.path.exists(filename):
                if file_type == 'nc':
                    # Abrir el archivo .nc y agregarlo a la lista de datasets
                    ds = xr.open_dataset(filename)
                    datasets.append(ds)
                    times.append(date)
                elif file_type == 'tif':
                    # Abrir el archivo .tif y agregarlo a la lista de datasets
                    with rasterio.open(filename) as src:
                        data = src.read(1)  # Leer la primera banda
                        latitudes = src.transform[5] + src.transform[4] * np.arange(src.height)
                        longitudes = src.transform[2] + src.transform[0] * np.arange(src.width)
                        ds = xr.DataArray(
                            data,
                            dims=('lat', 'lon'),
                            coords={
                                'lat': latitudes,
                                'lon': longitudes
                            },
                            name=variable_name
                        ).to_dataset(name=variable_name)  # Convertir DataArray a Dataset
                        datasets.append(ds)
                        times.append(date)
                else:
                    print(f'Unsupported file type: {file_type}')
                    return
            else:
                print(f'File not found: {filename}')

        # Combinar todos los datasets en uno solo a lo largo de la dimensión 'time'
        combined_ds = xr.concat(datasets, dim='time')
        combined_ds['time'] = times  # Asignar la coordenada de tiempo

        # Asignar las unidades a la variable
        combined_ds[variable_name].attrs['units'] = units
        
        # Guardar el dataset combinado a un archivo .nc
        combined_ds.to_netcdf(output_folder, mode='w', format='NETCDF4')
        print(combined_ds)

        # Cerrar los datasets
        for ds in datasets:
            ds.close()


        
    def translate_julian_dates(self, directorio):
        # Obtener una lista de los archivos en el directorio
        archivos = os.listdir(directorio)
        
        # Crear una lista para almacenar los nuevos nombres de archivos
        nuevos_nombres = []
        
        # Iterar sobre los archivos
        for archivo in archivos:
            # Asumimos que los nombres de los archivos tienen el formato '2024099.ext'
            nombre, extension = os.path.splitext(archivo)
            
            if len(nombre) == 7 and nombre.isdigit():
                año = int(nombre[:4])
                dia_juliano = int(nombre[4:])
                
                # Convertir el día juliano a una fecha
                fecha = datetime.strptime(f'{año}{dia_juliano:03}', '%Y%j').strftime('%Y-%m-%d')
                
                # Crear el nuevo nombre de archivo
                nuevo_nombre = f'{fecha}{extension}'
                
                # Añadir el nuevo nombre a la lista
                nuevos_nombres.append(nuevo_nombre)
                
                # Renombrar el archivo en el sistema de archivos
                os.rename(os.path.join(directorio, archivo), os.path.join(directorio, nuevo_nombre))
            else:
                nuevos_nombres.append(archivo)
        
        return nuevos_nombres

    def calculate_daily_mean_per_municipality(self, shapefile_path, netcdf_file, variable_name, region_column, municipality_column, units):
        """
        Función para calcular el promedio diario de una variable por municipio y escribir los resultados en un archivo CSV.

        Parámetros:
        - shapefile_path: Ruta al shapefile de municipios.
        - netcdf_file: Ruta al archivo NetCDF.
        - variable_name: Nombre de la variable en el archivo NetCDF.
        - output_csv: Ruta donde se guardará el archivo CSV de salida.
        - region_column: Nombre de la columna en el shapefile que contiene la región.
        - municipality_column: Nombre de la columna en el shapefile que contiene el nombre del municipio.
        - units: Unidades de la variable.
        """
        # Cargar el shapefile de municipios
        municipalities = gpd.read_file(shapefile_path)

        # Abrir el archivo NetCDF
        dataset = xr.open_dataset(netcdf_file)

        # Verificar si la variable existe en el conjunto de datos
        if variable_name not in dataset:
            raise ValueError(f"La variable '{variable_name}' no se encuentra en el archivo NetCDF.")

        # Inicializar una lista para almacenar los resultados
        results = []

        # Obtener las dimensiones del archivo NetCDF
        lon_dim = 'lon' if 'lon' in dataset.dims else 'x'
        lat_dim = 'lat' if 'lat' in dataset.dims else 'y'

        # Iterar sobre cada municipio y calcular el promedio diario
        for index, municipality in municipalities.iterrows():
            # Obtener el polígono del municipio
            municipality_polygon = municipality['geometry']

            # Extraer los datos de la variable para el polígono del municipio
            variable_data = dataset[variable_name].sel({lon_dim: municipality_polygon.centroid.x, lat_dim: municipality_polygon.centroid.y}, method='nearest')

            # Calcular el promedio diario
            daily_mean = variable_data.mean(dim='time').values

            # Agregar los resultados a la lista
            results.append({
                'region': municipality[region_column],
                'municipio': municipality[municipality_column],
                f'{variable_name}_promedio ({units})': daily_mean
            })

        # Crear un DataFrame con los resultados y escribirlo en un archivo CSV
        df = pd.DataFrame(results)
        #df.to_csv(output_csv, index=False)
        return df


#regions_crop("./outputs/MSWX/2024jun28/ET0.nc", "./mask_honduras/regions_shapefile/hnd_admbnda_adm1_sinit_20161005.shp", "./outputs/MSWX/ET0_Honduras_regions.nc")
# ini_date = datetime(2017, 8, 15).date()
# fin_date = datetime(2017, 8, 25).date()
# #merge_files(ini_date, fin_date, "./forecast_data/RAINNC/RAINNC_", "./outputs/forecast/RAINNC_forecast_Honduras.nc", "tif", variable_name='precipitation')
# #merge_files(ini_date, fin_date, "./forecast_data/ET0/ET0_", "./outputs/forecast/ET0_forecast_Honduras.nc", "tif", variable_name='ET0')
# # Ejemplo de uso
# plot_nc_file("./outputs/IMERG/IMERG_Honduras.nc", "precipitationCal")
# plot_nc_file("./outputs/MSWX/2024jun28/ET0_Honduras.nc", "ET0")
#plot_nc_file("./outputs/forecast/ET0_forecast_Honduras.nc", "ET0", lon_dim='x', lat_dim='y', time_dim='time')
#plot_nc_file("./outputs/forecast/RAINNC_forecast_Honduras.nc", "precipitation", lon_dim='x', lat_dim='y', time_dim='time')


if __name__ == "__main__":
    #Dates for last ten days, taking yesterday as last day

    ini_date = datetime(2024, 4, 8).date()
    fin_date = datetime(2024, 4, 18).date() 
    main = Tools()


    #nuevos_nombres = main.translate_julian_dates("./workspace/inputs/downloaded_data/20240705/MSWX/Temp/")

    #main.merge_files(ini_date, fin_date, "./workspace/inputs/downloaded_data/20240705/MSWX/Temp/", "./workspace/outputs/20240705/MSWX/Temp.nc", "nc", "degree_Celsius", variable_name='air_temperature')
    #main.country_crop("./workspace/outputs/20240705/MSWX/Temp.nc", "./workspace/config/mask_honduras/mask_mswx_hnd.nc4", "./workspace/outputs/20240705/MSWX/Temp_Honduras.nc")
    #main.regions_crop("./workspace/outputs/20240710/MSWX/Temp_Honduras.nc", "./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/20240705/MSWX/Temp_Honduras_municipios.nc", "NAME_2")
    
    #main.regions_crop("./workspace/outputs/20240705/MSWX/Temp_Honduras.nc", "./workspace/config/mask_honduras/regions_shapefile/Regiones_productoras_HN.shp", "./workspace/outputs/20240710/MSWX/Temp_Honduras_regions.nc", "Nombre")
    main.regions_crop("./workspace/outputs/20240710/MSWX/ET0_Honduras.nc", "./workspace/config/mask_honduras/regions_shapefile/Regiones_productoras_HN.shp", "./workspace/outputs/20240710/MSWX/ET0_Honduras_regions.nc", "Nombre")
    #main.regions_crop("./workspace/outputs/20240710/IMERG/IMERG_Honduras.nc", "./workspace/config/mask_honduras/regions_shapefile/Regiones_productoras_HN.shp", "./workspace/outputs/20240710/IMERG/IMERG_Honduras_regions.nc", "Nombre")
    #main.regions_crop("./workspace/outputs/20240710/forecast/ET0_forecast_Honduras.nc", "./workspace/config/mask_honduras/regions_shapefile/Regiones_productoras_HN.shp", "./workspace/outputs/20240710/forecast/ET0_forecast_Honduras_regions.nc", "Nombre")
    #main.regions_crop("./workspace/outputs/20240710/forecast/RAINNC_forecast_Honduras.nc", "./workspace/config/mask_honduras/regions_shapefile/Regiones_productoras_HN.shp", "./workspace/outputs/20240710/forecast/RAINNC_forecast_Honduras_regions.nc", "Nombre")

    #main.plot_nc_file("./workspace/outputs/20240705/MSWX/Temp_Honduras.nc", "air_temperature", save_path="./workspace/outputs/figures/",lon_dim='lon', lat_dim='lat', time_dim='time')
    #main.calculate_daily_mean_per_municipality("./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/20240705/MSWX/Temp_Honduras.nc", "air_temperature", "./workspace/outputs/20240705/MSWX/Temp_Honduras_municipios.csv", "NAME_1", "NAME_2", "grados celcius")
    #main.calculate_daily_mean_per_municipality("./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/20240705/MSWX/ET0_Honduras.nc", "ET0", "./workspace/outputs/20240705/MSWX/ET0_Honduras_municipios.csv", "NAME_1", "NAME_2", "mm/day")
    #main.calculate_daily_mean_per_municipality("./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/20240704/IMERG/IMERG_Honduras.nc", "precipitationCal", "./workspace/outputs/20240704/IMERG/IMERG_Honduras_municipios.csv", "NAME_1", "NAME_2", "mm/day")
    #main.calculate_daily_mean_per_municipality("./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/forecast/ET0_forecast_Honduras.nc", "ET0", "./workspace/outputs/forecast/ET0_forecast_Honduras_municipios.csv", "NAME_1", "NAME_2", "mm/day")
    #main.calculate_daily_mean_per_municipality("./workspace/config/mask_honduras/municipalities_shapefile/Municipios_reg_prod_HN.shp", "./workspace/outputs/forecast/RAINNC_forecast_Honduras.nc", "precipitation", "./workspace/outputs/forecast/RAINNC_forecast_Honduras_municipios.csv", "NAME_1", "NAME_2", "mm/day")
