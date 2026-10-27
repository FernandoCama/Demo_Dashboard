import unittest
from unittest.mock import Mock, patch

import pandas as pd

import app as dashboard
from conexion_sheets import (
    ErrorRegistro,
    aprobar_registro,
    actualizar_estado_registro,
    marcar_registro_notificado,
)


HEADERS = [
    'CÓDIGO',
    'Nombres y apellidos',
    'Correo electrónico',
    'Monto declarado',
    'CONTROL DE LEY',
    'ESTADO DE VALIDACIÓN',
    'NOTIFICADO',
    'Firma',
    'Fórmula auxiliar',
]


def filas_hoja(estado='PENDIENTE', control='Dentro del límite', monto='40.00'):
    return [
        HEADERS,
        ['VG-001', 'Ana Pérez', 'ana@example.test', monto, control, estado, 'No', '', '=SUM(1,1)'],
    ]


class ApprovalSheetTests(unittest.TestCase):
    def test_approval_updates_only_status_cell_by_unique_code(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [filas_hoja(), filas_hoja(estado='APROBADO')]

        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = aprobar_registro('VG-001', 45.20)

        hoja.update_cell.assert_called_once_with(2, 6, 'APROBADO')
        self.assertEqual(resultado['codigo'], 'VG-001')
        self.assertEqual(resultado['nombre'], 'Ana Pérez')
        self.assertEqual(resultado['correo'], 'ana@example.test')

    def test_approval_uses_current_limit_parameter(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(monto='50.00'), filas_hoja(estado='APROBADO', monto='50.00')
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            aprobar_registro('VG-001', 55)
        hoja.update_cell.assert_called_once_with(2, 6, 'APROBADO')

    def test_approved_and_discarded_records_cannot_be_approved_again(self):
        for estado in ('APROBADO', 'DESCARTADO'):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(estado=estado)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    aprobar_registro('VG-001', 45.20)
            hoja.update_cell.assert_not_called()

    def test_control_and_limit_restrictions_are_checked_before_write(self):
        for control, monto in (
            ('Excede el límite', '40.00'),
            ('Dentro del límite', '50.00'),
            ('Dentro del límite', '0'),
            ('Dentro del límite', '-1'),
        ):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(control=control, monto=monto)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    aprobar_registro('VG-001', 45.20)
            hoja.update_cell.assert_not_called()

    def test_duplicate_code_is_rejected(self):
        hoja = Mock()
        hoja.get_all_values.return_value = filas_hoja() + [
            ['VG-001', 'Otra persona', 'otra@example.test', '20', 'Dentro del límite', 'PENDIENTE', 'No', '', '=1'],
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            with self.assertRaises(ErrorRegistro):
                aprobar_registro('VG-001', 45.20)
        hoja.update_cell.assert_not_called()

    def test_notification_flag_is_written_only_after_send_confirmation(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(estado='APROBADO'),
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = marcar_registro_notificado('VG-001')
        self.assertTrue(resultado)
        hoja.update_cell.assert_called_once_with(2, 7, 'SÍ')

    def test_repeated_approval_is_rejected_after_first_write(self):
        class HojaEnMemoria:
            def __init__(self):
                self.valores = filas_hoja()
                self.actualizaciones = []

            def get_all_values(self):
                return self.valores

            def update_cell(self, fila, columna, valor):
                self.actualizaciones.append((fila, columna, valor))
                self.valores[fila - 1][columna - 1] = valor

        hoja = HojaEnMemoria()
        with patch('conexion_sheets.conectar', return_value=hoja):
            aprobar_registro('VG-001', 45.20)
            with self.assertRaises(ErrorRegistro):
                aprobar_registro('VG-001', 45.20)
        self.assertEqual(hoja.actualizaciones, [(2, 6, 'APROBADO')])

    def test_pending_record_can_be_rejected_by_unique_code(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(control='Excede el límite', monto='50'),
            filas_hoja(estado='DESCARTADO', control='Excede el límite', monto='50'),
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
        hoja.update_cell.assert_called_once_with(2, 6, 'DESCARTADO')
        self.assertEqual(resultado['estado'], 'DESCARTADO')

    def test_rejection_cannot_be_repeated_or_apply_to_non_pending_record(self):
        for estado in ('APROBADO', 'DESCARTADO'):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(estado=estado)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
            hoja.update_cell.assert_not_called()

    def test_sheet_write_failure_leaves_previous_status_untouched(self):
        class HojaEnMemoria:
            def __init__(self):
                self.valores = filas_hoja()

            def get_all_values(self):
                return self.valores

            def update_cell(self, fila, columna, valor):
                raise RuntimeError('Sheets API unavailable')

        hoja = HojaEnMemoria()
        with patch('conexion_sheets.conectar', return_value=hoja):
            with self.assertRaises(RuntimeError):
                actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
        self.assertEqual(hoja.valores[1][5], 'PENDIENTE')


class ApprovalApiTests(unittest.TestCase):
    def setUp(self):
        dashboard.app.config.update(TESTING=True)
        self.client = dashboard.app.test_client()
        self.data = pd.DataFrame([{
            'CÓDIGO': 'VG-001',
            'Nombres y apellidos': 'Ana Pérez',
            'Correo electrónico': 'ana@example.test',
            'Monto declarado': 40.0,
            'CONTROL DE LEY': 'Dentro del límite',
            'ESTADO DE VALIDACIÓN': 'PENDIENTE',
            'NOTIFICADO': 'No',
            'Firma': '',
        }])
        with patch.multiple(
            dashboard,
            obtener_datos=Mock(return_value=self.data),
            generar_graficos=Mock(),
            grafico_estados_interactivo=Mock(return_value=Mock(to_html=Mock(return_value=''))),
        ):
            response = self.client.get('/')
            self.dashboard_html = response.get_data(as_text=True)
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def post_approval(self):
        return self.client.post(
            '/api/registros/aprobar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )

    def post_rejection(self):
        return self.client.post(
            '/api/registros/rechazar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )

    def test_dashboard_renders_both_actions_without_extra_key(self):
        self.assertIn('id="aprobarRegistro"', self.dashboard_html)
        self.assertIn('id="rechazarRegistro"', self.dashboard_html)
        self.assertGreater(
            self.dashboard_html.index('id="modalDetalleRegistro"'),
            self.dashboard_html.index('</main>'),
        )
        self.assertIn('¿Deseas ${verbo} este registro?', self.dashboard_html)
        self.assertIn('Sí, ${verbo}', self.dashboard_html)
        self.assertIn('if (!confirmacion.isConfirmed)', self.dashboard_html)
        self.assertNotIn('Clave de aprobación', self.dashboard_html)
        self.assertNotIn('input: \'password\'', self.dashboard_html)

    @patch('app.marcar_registro_notificado', return_value=True)
    @patch('app.enviar_notificacion_aprobacion', return_value=True)
    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'APROBADO',
    })
    def test_api_notifies_only_after_persisted_approval(self, approve, send, mark):
        response = self.post_approval()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['guardado'])
        self.assertTrue(response.json['aprobado'])
        approve.assert_called_once_with('VG-001', 'APROBADO', dashboard.LIMITE_GASTO)
        send.assert_called_once()
        mark.assert_called_once_with('VG-001')

    @patch('app.enviar_notificacion_aprobacion', side_effect=dashboard.ErrorNotificacion('SMTP no configurado'))
    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'APROBADO',
    })
    def test_notification_failure_does_not_mark_notified(self, approve, send):
        with patch('app.marcar_registro_notificado') as mark:
            response = self.post_approval()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['aprobado'])
        self.assertFalse(response.json['notificacion']['enviado'])
        mark.assert_not_called()

    @patch('app.actualizar_estado_registro', side_effect=ErrorRegistro('Ya no está pendiente.', 409))
    @patch('app.enviar_notificacion_aprobacion')
    def test_failed_approval_never_sends_notification(self, send, approve):
        response = self.post_approval()
        self.assertEqual(response.status_code, 409)
        send.assert_not_called()

    @patch('app.actualizar_estado_registro', side_effect=RuntimeError('Sheets unavailable'))
    @patch('app.enviar_notificacion_aprobacion')
    def test_sheet_write_failure_returns_error_without_notification(self, send, update):
        response = self.post_rejection()
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json['ok'])
        send.assert_not_called()
        update.assert_called_once_with('VG-001', 'DESCARTADO', dashboard.LIMITE_GASTO)

    def test_missing_csrf_token_is_rejected(self):
        response = self.client.post('/api/registros/aprobar', json={'codigo': 'VG-001'})
        self.assertEqual(response.status_code, 403)

    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'DESCARTADO',
    })
    def test_rejection_persists_discarded_and_notifies_once(self, update):
        with patch('app.enviar_notificacion_aprobacion', return_value=True) as send, \
             patch('app.marcar_registro_notificado', return_value=True) as mark:
            response = self.post_rejection()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['estado'], 'DESCARTADO')
        self.assertTrue(response.json['rechazado'])
        update.assert_called_once_with('VG-001', 'DESCARTADO', dashboard.LIMITE_GASTO)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[-1], 'DESCARTADO')
        mark.assert_called_once_with('VG-001')

    @patch('app.marcar_registro_notificado', return_value=True)
    @patch('app.enviar_notificacion_aprobacion', return_value=True)
    @patch('app.actualizar_estado_registro', side_effect=[
        {
            'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
            'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
            'estado': 'APROBADO',
        },
        ErrorRegistro('Solo se pueden aprobar registros que continúan pendientes.', 409),
    ])
    def test_repeated_api_request_cannot_send_duplicate_notification(self, approve, send, mark):
        primera = self.post_approval()
        segunda = self.post_approval()
        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 409)
        send.assert_called_once()
        mark.assert_called_once_with('VG-001')


if __name__ == '__main__':
    unittest.main()
