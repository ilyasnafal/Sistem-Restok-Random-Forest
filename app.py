import streamlit as st
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error
from sklearn.model_selection import train_test_split
import datetime
import re

# Mengatur tampilan halaman menjadi mode lebar
st.set_page_config(page_title="Sistem Restock ML", layout="wide")

# ==============================================================================
# CSS KUSTOM UNTUK UI (TOMBOL LOGOUT & RADIO BUTTON TENGAH)
# ==============================================================================
st.markdown("""
    <style>
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #ff4c4c !important;
        color: white !important;
        border-color: #ff4c4c !important;
        transition: all 0.2s ease-in-out;
    }
    [data-testid="stSidebar"] .stButton > button {
        color: #ff4c4c !important;
        border-color: rgba(255, 76, 76, 0.5) !important;
    }
    section[data-testid="stMain"] .stRadio > label {
        display: flex;
        justify-content: center;
    }
    section[data-testid="stMain"] .stRadio > label p {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        margin-bottom: 0.5rem;
    }
    section[data-testid="stMain"] div[role="radiogroup"] {
        justify-content: center !important;
        gap: 3rem !important; 
    }
    section[data-testid="stMain"] div[role="radiogroup"] label p {
        font-size: 1.1rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. INISIALISASI SESSION STATE UNTUK DATA DINAMIS & LOGIN
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['role'] = None

if 'df_master' not in st.session_state:
    st.session_state['df_master'] = pd.DataFrame({
        'Nama Barang': ['Gelas Emas', 'Gelas Emas', 'Gelas Emas', 'Kindy Bag', 'Kindy Bag', 'Kindy Bag'],
        'Keuntungan': [3000, 3500, 3200, 11000, 12000, 11500],
        'Pendapatan': [6000, 7000, 6500, 50000, 55000, 52000],
        'Total':      [2, 3, 2, 1, 2, 1]
    })

if 'riwayat_forecast' not in st.session_state:
    st.session_state['riwayat_forecast'] = pd.DataFrame(columns=[
        'Waktu Peramalan', 'Nama Produk', 'Metode', 'Rekomendasi Kuantitas', 'Estimasi Waktu'
    ])

if 'last_uploaded' not in st.session_state:
    st.session_state['last_uploaded'] = None

# ==============================================================================
# 2. HALAMAN LOGIN
# ==============================================================================
if not st.session_state['logged_in']:
    st.markdown("<h2 style='text-align: center;'>🔑 Login Sistem Peramalan Restock</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            input_user = st.text_input("Username")
            input_pass = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Masuk ke Sistem")
            
            if submit_button:
                try:
                    if input_user == st.secrets["data_admin"]["username"] and input_pass == st.secrets["data_admin"]["password"]:
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "Admin"
                        st.rerun()
                    elif input_user == st.secrets["data_owner"]["username"] and input_pass == st.secrets["data_owner"]["password"]:
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "Owner"
                        st.rerun()
                    else:
                        st.error("Username atau Password Salah!")
                except KeyError:
                    if input_user == "admin123" and input_pass == "admin":
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "Admin"
                        st.rerun()
                    elif input_user == "owner123" and input_pass == "owner":
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "Owner"
                        st.rerun()
                    else:
                        st.error("Data kredensial tidak valid!")

# ==============================================================================
# 3. HALAMAN UTAMA APLIKASI
# ==============================================================================
else:
    role_user = st.session_state['role']

    # --------------------------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------------------------
    st.sidebar.markdown(f"**Status:** Login sebagai {role_user}")
    if st.sidebar.button("Keluar (Logout)"):
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.title("📂 Pengaturan Data")
    uploaded_file = st.sidebar.file_uploader("Timpa Master Stok dengan File (Excel/CSV)", type=["xlsx", "csv"])
    
    if uploaded_file is not None and uploaded_file.name != st.session_state['last_uploaded']:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df_temp = pd.read_excel(uploaded_file, header=None)
                header_idx = 0
                for i, row in df_temp.iterrows():
                    if any('nama' in str(item).lower() for item in row):
                        header_idx = i
                        break
                df_temp = pd.read_excel(uploaded_file, header=header_idx)
            else:
                df_temp = pd.read_csv(uploaded_file)
                
            df_temp.columns = [str(c).strip() for c in df_temp.columns]
            
            col_nama = [c for c in df_temp.columns if 'nama' in c.lower()][0]
            col_total = [c for c in df_temp.columns if 'total' in c.lower() or 'jumlah' in c.lower()][0]
            col_pendapatan = [c for c in df_temp.columns if 'pendapatan' in c.lower()][0]
            col_keuntungan = [c for c in df_temp.columns if 'keuntungan' in c.lower()][0]

            df_temp = df_temp.rename(columns={
                col_nama: 'Nama Barang', col_total: 'Total',
                col_pendapatan: 'Pendapatan', col_keuntungan: 'Keuntungan'
            })
            
            def bersihkan_angka(x):
                if pd.isna(x): return 0
                if isinstance(x, (int, float)): return int(x)
                x = str(x).lower().replace('rp', '').strip()
                if ',' in x: x = x.split(',')[0]
                x = x.replace('.', '')
                x = re.sub(r'[^0-9]', '', x)
                return int(x) if x else 0

            for col in ['Keuntungan', 'Pendapatan', 'Total']:
                df_temp[col] = df_temp[col].apply(bersihkan_angka)
                
            df_temp = df_temp.dropna(subset=['Total', 'Nama Barang'])
            
            st.session_state['df_master'] = df_temp
            st.session_state['last_uploaded'] = uploaded_file.name
            st.sidebar.success("✅ File berhasil dibersihkan dan dimuat ke Master Stok!")
            
        except Exception as e:
            st.sidebar.error(f"Gagal memproses file: {e}. Pastikan format sesuai.")

    df_clean = st.session_state['df_master']

    # --------------------------------------------------------------------------
    # KONTEN UTAMA: TABS
    # --------------------------------------------------------------------------
    st.title("Sistem Informasi Optimalisasi Restock berbasis Machine Learning")
    st.markdown("<br>", unsafe_allow_html=True)
    
    if role_user == "Owner":
        tabs = st.tabs(["🏠 Dashboard", "🔮 Forecasting", "📦 Master Stok", "💰 Keuangan"])
        tab_dash, tab_forecast, tab_stok, tab_keu = tabs
    else:
        tabs = st.tabs(["🏠 Dashboard", "📦 Master Stok", "➕ Input Data Baru"])
        tab_dash, tab_stok, tab_input = tabs

    # ==========================================================================
    # TAB DASHBOARD
    # ==========================================================================
    with tab_dash:
        st.header("Kinerja Ringkas Toko")
        total_sku = len(df_clean['Nama Barang'].unique())
        total_terjual = int(df_clean['Total'].sum())
        total_keuntungan = int(df_clean['Keuntungan'].sum())
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total SKU Produk", f"{total_sku} Item")
        col2.metric("Total Produk Terjual", f"{total_terjual} Unit")
        col3.metric("Total Keuntungan", f"Rp {total_keuntungan:,.0f}")
        
        st.markdown("---")
        st.subheader("📊 Tren Volume Transaksi Keseluruhan")
        st.line_chart(df_clean[['Total']].copy())

    # ==========================================================================
    # TAB FORECASTING (OWNER)
    # ==========================================================================
    if role_user == "Owner":
        with tab_forecast:
            st.header("🔮 Peramalan Kuantitas Restock")
            st.markdown("<br>", unsafe_allow_html=True)
            col_form, col_hasil = st.columns([1, 1.2])
            
            with col_form:
                with st.container(border=True):
                    with st.form("owner_forecast_form", border=False):
                        metode_pilihan = st.selectbox("Pilih Metode Peramalan:", ["Random Forest Regressor", "Regresi Linier", "Keduanya"])
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        daftar_produk = df_clean['Nama Barang'].unique().tolist()
                        produk_pilihan = st.selectbox("Pilih Produk yang Ingin Diprediksi:", daftar_produk)
                        
                        st.markdown("<hr>", unsafe_allow_html=True)
                        
                        hitung_estimasi_waktu = st.checkbox("Saya ingin memprediksi kapan waktu restock (membutuhkan data sisa stok saat ini)", value=False)
                        if hitung_estimasi_waktu:
                            stok_saat_ini = st.number_input("Sisa Stok di Gudang Saat Ini (Unit):", min_value=0, value=0, step=1)
                        else:
                            stok_saat_ini = 0
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        submit_owner = st.form_submit_button("Lakukan Peramalan")
                        
            with col_hasil:
                st.markdown("### Hasil Analisis & Keputusan")
                if submit_owner:
                    item_df = df_clean[df_clean['Nama Barang'] == produk_pilihan].copy()
                    
                    if len(item_df) >= 3:
                        X_item = item_df[['Keuntungan', 'Pendapatan']]
                        y_item = item_df['Total']
                        
                        X_train, X_test, y_train, y_test = train_test_split(X_item, y_item, test_size=0.2, random_state=42)
                        input_pred = pd.DataFrame([[item_df['Keuntungan'].mean(), item_df['Pendapatan'].mean()]], columns=['Keuntungan', 'Pendapatan'])
                        
                        waktu_sekarang = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        def latih_dan_tampilkan(nama_model, model_obj):
                            model_obj.fit(X_train, y_train)
                            y_pred_test = model_obj.predict(X_test)
                            mape_val = mean_absolute_percentage_error(y_test, y_pred_test)
                            
                            next_pred = model_obj.predict(input_pred)[0]
                            pred_riil = max(0, round(next_pred))
                            
                            if hitung_estimasi_waktu:
                                if pred_riil > 0:
                                    sisa_bulan = stok_saat_ini / pred_riil
                                    if sisa_bulan < 1:
                                        waktu_restock = "Segera (Bulan Ini)"
                                    elif 1 <= sisa_bulan < 2:
                                        waktu_restock = "Bulan Depan"
                                    else:
                                        waktu_restock = f"{int(sisa_bulan)} Bulan Lagi"
                                else:
                                    waktu_restock = "Belum Perlu (Prediksi Penjualan 0)"
                            else:
                                waktu_restock = "Bulan Depan (Berdasarkan 1 Periode Prediksi)"
                            
                            st.info(f"💡 Kuantitas Restock ({nama_model}): **{pred_riil} unit**")
                            st.warning(f"⏳ Perkiraan Harus Restock: **{waktu_restock}**")
                            st.success(f"📈 Akurasi Galat (MAPE): **{mape_val*100:.2f}%**")
                            st.markdown("<br>", unsafe_allow_html=True)
                            
                            riwayat_baru = pd.DataFrame([{
                                'Waktu Peramalan': waktu_sekarang, 
                                'Nama Produk': produk_pilihan, 
                                'Metode': nama_model, 
                                'Rekomendasi Kuantitas': f"{pred_riil} unit",
                                'Estimasi Waktu': waktu_restock
                            }])
                            st.session_state['riwayat_forecast'] = pd.concat([st.session_state['riwayat_forecast'], riwayat_baru], ignore_index=True)

                        if metode_pilihan in ["Random Forest Regressor", "Keduanya"]:
                            latih_dan_tampilkan("Random Forest", RandomForestRegressor(n_estimators=100, random_state=42))
                            
                        if metode_pilihan in ["Regresi Linier", "Keduanya"]:
                            latih_dan_tampilkan("Regresi Linier", LinearRegression())
                            
                    else:
                        st.error(f"⚠️ Riwayat data historis '{produk_pilihan}' kurang dari 3 baris ({len(item_df)} baris). Tidak dapat melakukan peramalan.")
                else:
                    st.write("Silakan isi form di sebelah kiri, lalu klik 'Lakukan Peramalan'.")

            st.markdown("<br><hr><br>", unsafe_allow_html=True)
            st.header("📋 Tabel Riwayat Hasil Peramalan Otomatis (Log Sistem)")
            if st.session_state['riwayat_forecast'].empty:
                st.info("Belum ada riwayat peramalan yang dicatat.")
            else:
                st.dataframe(st.session_state['riwayat_forecast'], use_container_width=True)

        # ==========================================================================
        # TAB KEUANGAN (FITUR BARU)
        # ==========================================================================
        with tab_keu:
            st.header("Laporan Keuangan & Profitabilitas")
            st.write("Menampilkan rekapitulasi finansial, perbandingan modal vs keuntungan, dan margin profit toko secara keseluruhan berdasarkan Master Stok.")
            
            if df_clean.empty:
                st.warning("Data Master Stok masih kosong.")
            else:
                # 1. Agregasi Data Keuangan per Produk
                df_keuangan = df_clean.groupby('Nama Barang').agg({
                    'Pendapatan': 'sum',
                    'Keuntungan': 'sum'
                }).reset_index()
                
                # 2. Menghitung Modal (HPP) dan Margin Profit
                df_keuangan['Modal (HPP)'] = df_keuangan['Pendapatan'] - df_keuangan['Keuntungan']
                df_keuangan['Margin Profit (%)'] = (df_keuangan['Keuntungan'] / df_keuangan['Pendapatan']) * 100
                df_keuangan['Margin Profit (%)'] = df_keuangan['Margin Profit (%)'].fillna(0) # Mencegah error pembagian dengan 0
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # --- ELEMEN 1: METRIK RINGKASAN ---
                st.subheader("1. Ringkasan Finansial Keseluruhan")
                total_pendapatan_all = df_keuangan['Pendapatan'].sum()
                total_keuntungan_all = df_keuangan['Keuntungan'].sum()
                total_modal_all = df_keuangan['Modal (HPP)'].sum()
                avg_margin_all = (total_keuntungan_all / total_pendapatan_all * 100) if total_pendapatan_all > 0 else 0
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.info(f"**Total Pendapatan:**\n### Rp {total_pendapatan_all:,.0f}")
                with col_m2:
                    st.warning(f"**Estimasi Total Modal:**\n### Rp {total_modal_all:,.0f}")
                with col_m3:
                    st.success(f"**Total Keuntungan:**\n### Rp {total_keuntungan_all:,.0f}")
                with col_m4:
                    st.error(f"**Rata-rata Margin:**\n### {avg_margin_all:.2f}%")
                
                st.markdown("<hr>", unsafe_allow_html=True)
                
                # --- ELEMEN 2: TABEL RINCIAN ---
                st.subheader("2. Tabel Rincian Finansial & Margin per Produk")
                df_tampil = df_keuangan.copy()
                df_tampil['Pendapatan'] = df_tampil['Pendapatan'].apply(lambda x: f"Rp {x:,.0f}")
                df_tampil['Modal (HPP)'] = df_tampil['Modal (HPP)'].apply(lambda x: f"Rp {x:,.0f}")
                df_tampil['Keuntungan'] = df_tampil['Keuntungan'].apply(lambda x: f"Rp {x:,.0f}")
                df_tampil['Margin Profit (%)'] = df_tampil['Margin Profit (%)'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(df_tampil, use_container_width=True)
                
                st.markdown("<hr>", unsafe_allow_html=True)
                
                # --- ELEMEN 3 & 4: GRAFIK VISUALISASI ---
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    st.subheader("3. Pendapatan vs Keuntungan")
                    st.write("Melihat perbandingan volume transaksi produk.")
                    chart_data = df_keuangan.set_index('Nama Barang')[['Pendapatan', 'Keuntungan']]
                    st.bar_chart(chart_data)
                
                with col_g2:
                    st.subheader("4. Tingkat Profitabilitas (Margin %)")
                    st.write("Semakin tinggi, semakin menguntungkan modalnya.")
                    margin_data = df_keuangan.sort_values(by='Margin Profit (%)', ascending=False)
                    chart_margin = margin_data.set_index('Nama Barang')[['Margin Profit (%)']]
                    st.bar_chart(chart_margin)

    # ==========================================================================
    # TAB INPUT DATA BARU (ADMIN)
    # ==========================================================================
    if role_user == "Admin":
        with tab_input:
            st.header("Input Data Baru")
            with st.container(border=True):
                mode_input = st.radio("Pilih Mode Input Data:", ["🔄 Update Produk yang Ada", "➕ Tambah Produk Baru"], horizontal=True)
                st.markdown("<hr>", unsafe_allow_html=True)
                
                if mode_input == "🔄 Update Produk yang Ada":
                    daftar_produk_admin = df_clean['Nama Barang'].unique().tolist()
                    nama_barang_final = st.selectbox("Pilih Produk yang akan diperbarui:", daftar_produk_admin)
                else:
                    nama_barang_final = st.text_input("Ketik Nama Produk Baru:", placeholder="Contoh: Tas Kanvas V2")
                    
                st.markdown("<br>", unsafe_allow_html=True)
                keuntungan_baru = st.number_input("Masukkan Keuntungan (Rp)", min_value=0, value=35000, step=1000)
                pendapatan_baru = st.number_input("Masukkan Pendapatan (Rp)", min_value=0, value=179000, step=5000)
                
                st.markdown("<br>", unsafe_allow_html=True)
                submit_admin = st.button("Simpan ke Master Stok", use_container_width=True)

            if submit_admin:
                if not nama_barang_final or not nama_barang_final.strip():
                    st.error("⚠️ Nama produk tidak boleh kosong!")
                else:
                    master_baru = pd.DataFrame([{
                        'Nama Barang': nama_barang_final.strip(), 'Keuntungan': keuntungan_baru, 
                        'Pendapatan': pendapatan_baru, 'Total': 0
                    }])
                    st.session_state['df_master'] = pd.concat([st.session_state['df_master'], master_baru], ignore_index=True)
                    st.success(f"✅ Data produk '{nama_barang_final.strip()}' berhasil ditambahkan ke dalam Master Stok.")

    # ==========================================================================
    # TAB MASTER STOK
    # ==========================================================================
    with tab_stok:
        st.header("Master Stok")
        st.dataframe(st.session_state['df_master'], use_container_width=True)
        csv_data = st.session_state['df_master'].to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Unduh Data Master Stok (CSV)", data=csv_data, file_name=f"Master_Stok_Terbaru_{datetime.date.today()}.csv", mime="text/csv")
