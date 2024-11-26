from io import BytesIO
import math
import ee
from PIL import Image
import requests
import streamlit as st
from datetime import datetime

# Earth Engineの初期化
ee.Authenticate()
ee.Initialize(project='your-project-id')


import math




def get_ndvi(image):
    """
    指定されたEarth Engine画像のNDVIを計算します。
    """
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    return ndvi

def get_image_in_memory(ee_image, scale: int, region) -> Image.Image:
    """
    Earth Engineから画像を取得し、PIL Imageとして返します。
    """
    url = ee_image.getThumbURL({
        'region': region,
        'scale': scale,
        'format': 'png',
        'crs': 'EPSG:4326',
    })
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    return image

def get_sentinel_image_collection(start_date, end_date, cloud_cover_rate, raw_coords):
    """
    ユーザー入力に基づいてフィルタリングされたSentinel-2画像コレクションを取得します。
    """
    # 座標を安全に解析
    try:
        coords = eval(raw_coords)
    except:
        raise ValueError("座標の形式が無効です。")

    area = {
        "coordinates": [coords],
        "type": "Polygon"
    }

    # 経度の補正が必要な場合
    adjusted_coords = []
    adjusted_coords.append([])
    for point in area['coordinates'][0]:
        adjusted_coords[0].append([point[0] + 360 if point[0] < 0 else point[0], point[1]])

    geometry = ee.Geometry.Polygon(adjusted_coords)

    # 画像コレクションを取得
    imgcol = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(geometry)
        .filterDate(ee.Date(start_date), ee.Date(end_date))
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_cover_rate))
        .sort('system:time_start', False)  # 日付で降順ソート
    )

    return imgcol, geometry

def main():
    st.title("GEE Sentinel-2 画像とNDVI画像viewer")

    # ユーザー入力
    st.sidebar.header("入力パラメータ")
    start_date = st.sidebar.text_input("開始日 (YYYY-MM-DD):", "2023-01-01")
    end_date = st.sidebar.text_input("終了日 (YYYY-MM-DD):", "2023-01-10")
    cloud_cover_rate = st.sidebar.slider("雲の被覆率 (%)", min_value=0, max_value=100, value=30)

    st.sidebar.write("観測領域の座標を入力してください (経度, 緯度).")
    raw_coords = st.sidebar.text_area(
        "座標",
        "[[-220.236491, 35.6363273], [-220.2358044, 35.6251654], [-220.2188743, 35.6253398], [-220.220033, 35.6367982]]"
    )

    # ページネーション用のセッションステート初期化
    if 'page' not in st.session_state:  
        st.session_state.page = 0
    if 'geometry' not in st.session_state:
        st.session_state.geometry = None

    # 画像コレクションの取得
    if st.sidebar.button("画像を取得する"):
        try:
            imgcol, geometry = get_sentinel_image_collection(start_date, end_date, cloud_cover_rate, raw_coords)
            image_count = imgcol.size().getInfo()
            st.session_state.image_list = imgcol.toList(image_count).reverse()  # 逆順にして保存
            st.session_state.total_pages = math.ceil(image_count / 4)
            st.session_state.page = 0  # 最初のページにリセット
            st.session_state.geometry = geometry  # geometryをセッションステートに保存
            if image_count == 0:
                st.sidebar.warning("指定した条件で画像が見つかりませんでした。")
        except Exception as e:
            st.sidebar.error(f"画像の取得中にエラーが発生しました: {e}")

    # 画像が取得されているか確認
    if 'image_list' in st.session_state and st.session_state.geometry is not None:
        image_list = st.session_state.image_list  # セッションステートから取得
        geometry = st.session_state.geometry
        total_pages = st.session_state.total_pages

        # ナビゲーションボタンのコールバック関数を定義
        def prev_page():
            if st.session_state.page > 0:
                st.session_state.page -= 1

        def next_page():
            if st.session_state.page < total_pages - 1:
                st.session_state.page += 1

        # ナビゲーションボタンを配置（current_pageを設定する前に）
        nav_cols = st.columns(2)
        with nav_cols[0]:
            st.button("前へ", on_click=prev_page)
        with nav_cols[1]:
            st.button("次へ", on_click=next_page)

        # current_pageをセッションステートから取得
        current_page = st.session_state.page
        images_per_page = 4
        start_idx = current_page * images_per_page
        end_idx = start_idx + images_per_page
        current_images = image_list.slice(start_idx, end_idx).getInfo()

        # ページ情報の表示
        st.write(f"ページ {current_page + 1} / {total_pages}")

        # Sentinel画像の表示
        st.subheader("Sentinel-2 RGB画像")
        sentinel_cols = st.columns(2)
        for i in range(4):
            with sentinel_cols[i % 2]:
                if i < len(current_images):
                    img_dict = current_images[i]
                    img = ee.Image(img_dict['id'])
                    rgb = img.select(['TCI_R', 'TCI_G', 'TCI_B'])
                    rgb_image = get_image_in_memory(rgb, scale=10, region=geometry)

                    # 画像の日付を取得
                    timestamp = img_dict['properties']['system:time_start']
                    img_date = datetime.utcfromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')

                    st.image(rgb_image, caption=img_date, use_column_width=True)
                else:
                    st.text("no image")

        # NDVI画像の表示（NDVIはいらないかも？）
        st.subheader("NDVI画像")
        ndvi_cols = st.columns(2)
        ndvi_params = {
            'min': -1,
            'max': 1,
            'palette': ['blue', 'white', 'green']
        }
        for i in range(4):
            with ndvi_cols[i % 2]:
                if i < len(current_images):
                    img_dict = current_images[i]
                    img = ee.Image(img_dict['id'])
                    ndvi = get_ndvi(img)
                    ndvi_visual = ndvi.visualize(**ndvi_params)
                    ndvi_image = get_image_in_memory(ndvi_visual, scale=10, region=geometry)

                    timestamp = img_dict['properties']['system:time_start']
                    img_date = datetime.utcfromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')

                    st.image(ndvi_image, caption=img_date, use_column_width=True)
                else:
                    st.text("no image")

    else:
        st.info("パラメータを入力し、「画像を取得する」をクリックしてください。Sentinel-2画像とNDVI画像が表示されます。")


if __name__ == "__main__":
    main()