from io import BytesIO

import ee
from PIL import Image
import requests
import streamlit as st

def get_ndvi(asset_id):
    # NDVI計算関数

    ndvi = (
        ee.Image(asset_id)
            .normalizedDifference(['B8', 'B4'])
            .rename('ndvi')
    )
    return ndvi

def get_image_in_memory(input_image, scale: int, coords) -> BytesIO:
    # 画像DL&ローカル保存関数

    url = input_image.getThumbURL({
        'region': ee.Geometry.Polygon(coords),
        'scale': scale,
        'format': 'png',
    })
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    return image

def get_sentinel_image(start_date, end_date, cloud_cover_rate, raw_coords):
    # ユーザー入力から画像取得関数

    area = {
        "coordinates": [eval(raw_coords)],
        "type": "Polygon"
    }

    # 座標の補正
    coords = []
    coords.append([])
    for point in area['coordinates'][0]:
        coords[0].append([point[0] + 360, point[1]])

    # 画像コレクションを取得
    imgcol = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(ee.Geometry.Polygon(coords))
        .filterDate(ee.Date(start_date), ee.Date(end_date))
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_cover_rate))
    )

    image_count = imgcol.size().getInfo()
    # st.write(f"取得した画像枚数: {image_count}")

    if image_count > 0:
        # モザイク画像の作成（RGB画像）
        image = imgcol.mosaic().select(['TCI_R', 'TCI_G', 'TCI_B'])
        SCALE = 10
        rgb_image = get_image_in_memory(image, SCALE, coords)
        st.image(rgb_image, caption="GEE画像", use_container_width=True)

        # NDVI画像の作成
        image_ndvi = imgcol.mosaic().normalizedDifference(['B8', 'B4']).rename('ndvi')
        ndvi_params = {
            'min': -1,
            'max': 1,
            'palette': ['blue', 'white', 'green']
        }
        image_ndvi_rgb = image_ndvi.visualize(**ndvi_params)
        ndvi_image = get_image_in_memory(image_ndvi_rgb, SCALE, coords)
        st.image(ndvi_image, caption="NDVI画像", use_container_width=True)


def main():

    st.title("GEE画像とNDVI画像の表示")

    # 認証と初期化
    ee.Authenticate()
    ee.Initialize(project='your-project-id')

    # ユーザー入力
    start_date = st.text_input("開始日 (YYYY-MM-DD):", "2023-01-01") # 開始日
    end_date = st.text_input("終了日 (YYYY-MM-DD):", "2023-01-10") # 終了日
    cloud_cover_rate = st.slider("雲の被覆率 (%)", min_value=0, max_value=100, value=30) # 雲の被覆率

    st.write("観測領域の座標を入力してください (緯度と経度のリスト)") # 緯度経度リスト
    raw_coords = st.text_area(
        "座標 (例: [[-220.236491, 35.6363273], [-220.2358044, 35.6251654], [-220.2188743, 35.6253398], [-220.220033, 35.6367982]])",
        "[[-220.236491, 35.6363273], [-220.2358044, 35.6251654], [-220.2188743, 35.6253398], [-220.220033, 35.6367982]]"
    )

    # TODO 緯度経度データバリデーション

    try:
        if st.button("画像を取得する"):
            get_sentinel_image(start_date, end_date, cloud_cover_rate, raw_coords)
        else:
            st.warning("指定した条件で画像が見つかりませんでした。")

    except Exception as e:
        st.error(f"入力エラー: {e}")

if __name__ == "__main__":
    main()