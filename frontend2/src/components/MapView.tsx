import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

// Fix default marker icon broken by webpack/vite asset pipeline
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

const DEFAULT_CENTER: [number, number] = [40.4168, -3.7038]
const DEFAULT_ZOOM = 6
const SELECTED_ZOOM = 15

interface MapPannerProps {
  position: [number, number]
  zoom?: number
}

function MapPanner({ position, zoom = SELECTED_ZOOM }: MapPannerProps) {
  const map = useMap()
  useEffect(() => {
    map.setView(position, zoom)
  }, [map, position, zoom])
  return null
}

export interface MapViewProps {
  position?: [number, number] | null
  zoom?: number
  height?: string
}

export function MapView({ position = null, zoom, height = '320px' }: MapViewProps) {
  return (
    <div style={{ height }} className="w-full rounded-xl overflow-hidden">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom={false}
        className="h-full w-full"
        style={{ height: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
          attribution="&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors"
        />
        {position && (
          <>
            <Marker position={position} />
            <MapPanner position={position} zoom={zoom ?? SELECTED_ZOOM} />
          </>
        )}
      </MapContainer>
    </div>
  )
}
