package com.pixsynq.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.pixsynq.app.ui.HomeScreen
import com.pixsynq.app.ui.theme.PixSynqTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PixSynqTheme {
                HomeScreen()
            }
        }
    }
}
