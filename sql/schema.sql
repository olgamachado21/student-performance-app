IF DB_ID('StudentPerformanceDB') IS NULL
BEGIN
    CREATE DATABASE StudentPerformanceDB;
END
GO

USE StudentPerformanceDB;
GO


-- Tabela: Students_Raw: Dados importados diretamente do ficheiro original
IF OBJECT_ID('dbo.Students_Raw', 'U') IS NOT NULL
    DROP TABLE dbo.Students_Raw;
GO

CREATE TABLE dbo.Students_Raw (
    student_id      INT IDENTITY(1,1) PRIMARY KEY,
    school          NVARCHAR(10),
    sex             NVARCHAR(5),
    age             INT,
    address         NVARCHAR(5),
    famsize         NVARCHAR(10),
    Pstatus         NVARCHAR(5),
    Medu            INT,
    Fedu            INT,
    Mjob            NVARCHAR(20),
    Fjob            NVARCHAR(20),
    reason          NVARCHAR(20),
    guardian        NVARCHAR(20),
    traveltime      INT,
    studytime       INT,
    failures        INT,
    schoolsup       NVARCHAR(5),
    famsup          NVARCHAR(5),
    paid            NVARCHAR(5),
    activities      NVARCHAR(5),
    nursery         NVARCHAR(5),
    higher          NVARCHAR(5),
    internet        NVARCHAR(5),
    romantic        NVARCHAR(5),
    famrel          INT,
    freetime        INT,
    goout           INT,
    Dalc            INT,
    Walc            INT,
    health          INT,
    absences        INT,
    G1              INT,
    G2              INT,
    G3              INT
);
GO

-- ----------------------------------------------------------------------------
-- Tabela: Students_Clean: Dados após limpeza, tratamento de outliers, normalização e criação de novas variáveis.
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.Students_Clean', 'U') IS NOT NULL
    DROP TABLE dbo.Students_Clean;
GO

CREATE TABLE dbo.Students_Clean (
    student_id          INT PRIMARY KEY,
    school              NVARCHAR(10),
    sex                 NVARCHAR(5),
    age                 INT,
    address             NVARCHAR(5),
    famsize             NVARCHAR(10),
    Pstatus             NVARCHAR(5),
    Medu                INT,
    Fedu                INT,
    Mjob                NVARCHAR(20),
    Fjob                NVARCHAR(20),
    reason              NVARCHAR(20),
    guardian            NVARCHAR(20),
    traveltime          INT,
    studytime           INT,
    failures            INT,
    schoolsup           NVARCHAR(5),
    famsup              NVARCHAR(5),
    paid                NVARCHAR(5),
    activities          NVARCHAR(5),
    nursery             NVARCHAR(5),
    higher              NVARCHAR(5),
    internet            NVARCHAR(5),
    romantic            NVARCHAR(5),
    famrel              INT,
    freetime            INT,
    goout               INT,
    Dalc                INT,
    Walc                INT,
    health              INT,
    absences            INT,
    absences_is_outlier BIT,
    G1                  INT,
    G2                  INT,
    G3                  INT,
    aprovado            BIT,
    alcohol_avg         FLOAT,
    parent_edu_avg      FLOAT,
    grade_trend         INT,
    studytime_norm      FLOAT,
    absences_norm       FLOAT,
    G3_norm             FLOAT,
    FOREIGN KEY (student_id) REFERENCES dbo.Students_Raw(student_id)
);
GO

-- Views úteis para consulta rápida / dashboards
IF OBJECT_ID('dbo.vw_KPIs_Gerais', 'V') IS NOT NULL
    DROP VIEW dbo.vw_KPIs_Gerais;
GO

CREATE VIEW dbo.vw_KPIs_Gerais AS
SELECT
    COUNT(*)                                   AS total_estudantes,
    AVG(CAST(G3 AS FLOAT))                     AS nota_media,
    AVG(CAST(aprovado AS FLOAT))               AS taxa_aprovacao,
    AVG(CAST(absences AS FLOAT))                AS faltas_media,
    AVG(CAST(studytime AS FLOAT))               AS tempo_estudo_medio
FROM dbo.Students_Clean;
GO

IF OBJECT_ID('dbo.vw_Aprovacao_Por_TempoEstudo', 'V') IS NOT NULL
    DROP VIEW dbo.vw_Aprovacao_Por_TempoEstudo;
GO

CREATE VIEW dbo.vw_Aprovacao_Por_TempoEstudo AS
SELECT
    studytime,
    COUNT(*)                     AS n_estudantes,
    AVG(CAST(aprovado AS FLOAT)) AS taxa_aprovacao,
    AVG(CAST(G3 AS FLOAT))       AS nota_media
FROM dbo.Students_Clean
GROUP BY studytime;
GO

PRINT 'Esquema StudentPerformanceDB criado com sucesso.';
