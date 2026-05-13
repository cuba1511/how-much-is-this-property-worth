import { MapContainer, TileLayer, Marker, Circle, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

const propertyIcon = new L.Icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
  className: 'property-marker-highlight',
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
  radiusMeters?: number
  propertyPosition?: [number, number] | null
}

export function MapView({
  position = null,
  zoom,
  height = '320px',
  radiusMeters,
  propertyPosition,
}: MapViewProps) {
  const mainPos = propertyPosition ?? position
  const effectiveZoom = zoom ?? (radiusMeters ? zoomForRadius(radiusMeters) : SELECTED_ZOOM)

  return (
    <div style={{ height }} className="w-full overflow-hidden">
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

        {propertyPosition && (
          <Marker position={propertyPosition} icon={propertyIcon} />
        )}

        {position && !propertyPosition && (
          <Marker position={position} />
        )}

        {mainPos && radiusMeters && (
          <Circle
            center={mainPos}
            radius={radiusMeters}
            pathOptions={{
              color: 'hsl(225, 93%, 54%)',
              fillColor: 'hsl(225, 93%, 54%)',
              fillOpacity: 0.08,
              weight: 1.5,
            }}
          />
        )}

        {mainPos && (
          <MapPanner position={mainPos} zoom={effectiveZoom} />
        )}
      </MapContainer>
    </div>
  )
}

function zoomForRadius(radius: number): number {
  if (radius <= 200) return 17
  if (radius <= 600) return 15
  if (radius <= 2000) return 14
  return 13
}
