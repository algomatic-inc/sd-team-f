import datetime
import calendar

import ee
import folium
import streamlit as st
from streamlit_folium import folium_static

# google earth engine初期化
ee.Initialize()

def get_last_day_of_month(year, month):
    """指定された年と月の最終日を取得する関数"""
    last_day = calendar.monthrange(year, month)[1]
    return last_day

def maskS2clouds(image):
    """Sentinel-2画像から雲を除去するマスク関数"""
    qa = image.select('QA60')  # 雲データマスク処理用のバンドを抽出
    cloudBitMask = 1 << 10  # 雲の情報(bit)
    cirrusBitMask = 1 << 11  # 巻雲の情報(bit)
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))  # 雲,巻雲のピクセル除去フィルタ設定
    return image.updateMask(mask).divide(10000)  # マスク適用

def calc_ndvi(image):
    """NDVI計算関数"""
    return ee.Image(image.expression(
        '(NIR - RED) / (NIR + RED)', {  # NDVIの計算
            'RED': image.select('B4'),  # 赤色光データの抽出
            'NIR': image.select('B8')   # 近赤外線データの抽出
    }))

def get_satellite_data(year_start, year_end, lat, lon, height, width, exclude_winter):
    """指定された範囲と年の衛星画像データを取得"""
    # 地理的範囲を定義
    geometry = ee.Geometry.Rectangle([
        lon - width/2,
        lat - height/2,
        lon + width/2,
        lat + height/2
    ])

    # Sentinel-2コレクションを取得
    Sentinel2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(geometry)

    # データ取得期間の設定
    if exclude_winter:
        # 冬を除外する場合：06-01〜11-01
        start_date_start = f'{year_start}-06-01'
        end_date_start = f'{year_start}-10-31'
        start_date_end = f'{year_end}-06-01'
        end_date_end = f'{year_end}-10-31'
    else:
        # 全期間を含む場合：01-01〜12-31
        start_date_start = f'{year_start}-01-01'
        end_date_start = f'{year_start}-12-31'
        start_date_end = f'{year_end}-01-01'
        end_date_end = f'{year_end}-12-31'

    # 画像コレクションをフィルタリング
    year_start_collection = Sentinel2.filterDate(start_date_start, end_date_start) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10)) \
        .map(maskS2clouds) \
        .filterBounds(geometry)

    year_end_collection = Sentinel2.filterDate(start_date_end, end_date_end) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10)) \
        .map(maskS2clouds) \
        .filterBounds(geometry)

    # RGB画像取得
    rgb_start = year_start_collection.median()
    rgb_end = year_end_collection.median()

    # NDVI計算&取得
    ndvi_start = year_start_collection.map(calc_ndvi).median()
    ndvi_end = year_end_collection.map(calc_ndvi).median()

    # NDVI差分取得
    ndvi_difference = ndvi_end.subtract(ndvi_start)

    return ndvi_start, ndvi_end, rgb_start, rgb_end, ndvi_difference, geometry

def create_folium_map(ndvi_start, ndvi_end, rgb_start, rgb_end, ndvi_difference, geometry):
    """Foliumマップを作成する関数"""
    # マップの中心座標を取得
    center = geometry.centroid().coordinates().getInfo()
    my_map = folium.Map(location=[center[1], center[0]], zoom_start=10)

    # 可視化パラメータ
    visualization_rgb = {
        'min': 0.0,
        'max': 0.3,
        'bands': ['B4', 'B3', 'B2']
    }
    visualization_ndvi = {
        'min': 0,
        'max': 1,
        # 'palette': cc.rainbow
    }

    # レイヤーを追加する関数
    def add_ee_layer(ee_image_object, vis_params, name):
        map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id_dict['tile_fetcher'].url_format,
            attr='Map Data © Google Earth Engine',
            name=name,
            overlay=True,
            control=True
        ).add_to(my_map)

    # レイヤー追加
    add_ee_layer(ndvi_start, visualization_ndvi, f'NDVI {st.session_state.year_start}')
    add_ee_layer(ndvi_end, visualization_ndvi, f'NDVI {st.session_state.year_end}')
    add_ee_layer(ndvi_difference, visualization_ndvi, f'NDVI Difference')
    add_ee_layer(rgb_start, visualization_rgb, f'RGB {st.session_state.year_start}')
    add_ee_layer(rgb_end, visualization_rgb, f'RGB {st.session_state.year_end}')

    my_map.add_child(folium.LayerControl())
    return my_map

def main():
    current_year = datetime.datetime.now().year

    st.title('植生状況解析アプリ')

    # サイドバーに入力フォーム
    st.sidebar.header('パラメータ設定')
    year_start = st.sidebar.number_input('開始年', min_value=2015, max_value=current_year, value=2019)
    year_end = st.sidebar.number_input('終了年', min_value=2015, max_value=current_year, value=2023)
    lat = st.sidebar.number_input('緯度', min_value=-90.0, max_value=90.0, value=38.00)
    lon = st.sidebar.number_input('経度', min_value=-180.0, max_value=180.0, value=140.91)
    height = st.sidebar.number_input('高さ（度）', min_value=0.01, max_value=10.0, value=1.00)
    width = st.sidebar.number_input('幅（度）', min_value=0.01, max_value=10.0, value=0.01)
    exclude_winter = st.sidebar.checkbox('冬の期間を除外する')

    # セッション状態に保存
    st.session_state.year_start = year_start
    st.session_state.year_end = year_end

    if st.sidebar.button('データ取得と解析'):
        try:
            # データ取得
            ndvi_start, ndvi_end, rgb_start, rgb_end, ndvi_difference, geometry = get_satellite_data(
                year_start, year_end, lat, lon, height, width, exclude_winter
            )

            # 解析結果の表示
            st.subheader('解析結果')

            # Foliumマップの作成と表示
            my_map = create_folium_map(
                ndvi_start, ndvi_end, rgb_start, rgb_end, ndvi_difference, geometry
            )
            folium_static(my_map, width=800, height=600)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

if __name__ == '__main__':
    main()